import uuid

from inngest import NonRetriableError
from sqlalchemy.orm import Session

from app.config.database import SessionLocal
from app.repositories.background_job_repository import (
    get_by_id_for_update,
    mark_job_running,
    mark_job_succeeded,
    mark_job_failed,
)
from app.repositories.job_failure_repository import record_failure
from app.services.usage_report_service import generate_usage_report


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(job_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise NonRetriableError(
            "Invalid background job ID."
        ) from exc


def complete_usage_report_job(
    db: Session,
    job_id: str,
) -> dict:
    parsed_id = _parse_job_id(job_id)

    job = get_by_id_for_update(db, parsed_id)

    if job is None:
        raise NonRetriableError(
            "Background job does not exist."
        )

    if job.status == "succeeded":
        return job.result or {}

    if job.status == "failed":
        raise NonRetriableError(
            "Background job has permanently failed."
        )

    result = generate_usage_report(
        db,
        tenant_id=job.tenant_id,
        period_start=job.period_start,
    )

    mark_job_succeeded(
        db,
        job_id=parsed_id,
        result=result,
    )

    return result


def process_usage_report_job(job_id: str) -> dict:
    parsed_id = _parse_job_id(job_id)

    # Commit running status separately so it remains visible
    # while report processing is taking place.
    with SessionLocal.begin() as db:
        job = get_by_id_for_update(db, parsed_id)

        if job is None:
            raise NonRetriableError(
                "Background job does not exist."
            )

        if job.status == "succeeded":
            return job.result or {}

        if job.status == "failed":
            raise NonRetriableError(
                "Background job has permanently failed."
            )

        mark_job_running(db, parsed_id)

    # Report generation and result persistence are atomic.
    with SessionLocal.begin() as db:
        return complete_usage_report_job(
            db,
            str(parsed_id),
        )


def persist_usage_report_failure(
    db: Session,
    *,
    job_id: str,
    error_message: str,
) -> None:
    try:
        parsed_id = uuid.UUID(str(job_id))
    except (ValueError, TypeError, AttributeError):
        parsed_id = None

    if parsed_id is not None:
        job = get_by_id_for_update(db, parsed_id)

        if job is not None:
            if job.status == "succeeded":
                return

            mark_job_failed(db, parsed_id)

    record_failure(
        db,
        function_id="generate-usage-report",
        job_id=str(job_id),
        error_message=error_message,
    )
