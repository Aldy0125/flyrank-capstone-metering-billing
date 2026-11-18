import uuid
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from inngest import Event

from app.api.deps import get_db
from app.integrations.inngest import inngest_client
from app.repositories.tenant_repository import get_by_id as get_tenant_by_id
from app.repositories.background_job_repository import (
    create_usage_report_job,
    get_by_id_for_tenant,
)
from app.services.usage_report_worker import (
    persist_usage_report_failure,
)


router = APIRouter(
    prefix="/v1/usage/reports",
    tags=["Usage Reports"],
)


@router.post("", status_code=202)
async def request_usage_report(
    tenant_id: Annotated[
        uuid.UUID,
        Header(alias="X-Tenant-ID"),
    ],
    period_start: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    tenant = get_tenant_by_id(db, tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found.",
        )

    if period_start is None:
        now = datetime.now(timezone.utc)
        period_start = date(now.year, now.month, 1)

    if period_start.day != 1:
        raise HTTPException(
            status_code=422,
            detail="period_start must be the first day of a month.",
        )

    job = create_usage_report_job(
        db,
        tenant_id=tenant_id,
        period_start=period_start,
    )

    job_id = str(job.id)

    # Persist job before dispatch to avoid a worker receiving
    # an event for a job that does not exist yet.
    db.commit()

    try:
        await inngest_client.send(
            Event(
                name="billing/usage-report.requested",
                id=job_id,
                data={"job_id": job_id},
            )
        )
    except Exception as exc:
        db.rollback()

        try:
            with db.begin():
                persist_usage_report_failure(
                    db,
                    job_id=job_id,
                    error_message=f"Event dispatch failed: {exc}",
                )
        except Exception:
            db.rollback()
            raise

        raise HTTPException(
            status_code=503,
            detail="Unable to dispatch usage report job.",
        ) from exc

    return {
        "job_id": job_id,
        "status": "queued",
        "period_start": period_start.isoformat(),
    }


@router.get("/{job_id}")
def get_usage_report_status(
    job_id: uuid.UUID,
    tenant_id: Annotated[
        uuid.UUID,
        Header(alias="X-Tenant-ID"),
    ],
    db: Session = Depends(get_db),
):
    job = get_by_id_for_tenant(
        db,
        job_id=job_id,
        tenant_id=tenant_id,
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Usage report job not found.",
        )

    return {
        "job_id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "period_start": job.period_start.isoformat(),
        "result": job.result,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }
