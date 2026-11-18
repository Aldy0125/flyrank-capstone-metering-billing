import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.background_job import BackgroundJob


def create_usage_report_job(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    period_start: date,
) -> BackgroundJob:

    job = BackgroundJob(
        tenant_id=tenant_id,
        job_type="usage_report",
        status="queued",
        period_start=period_start,
    )

    db.add(job)
    db.flush()

    return job


def get_by_id(db: Session, job_id: uuid.UUID):
    return db.get(BackgroundJob, job_id)


def get_by_id_for_tenant(
    db: Session,
    *,
    job_id: uuid.UUID,
    tenant_id: uuid.UUID,
):
    statement = select(BackgroundJob).where(
        BackgroundJob.id == job_id,
        BackgroundJob.tenant_id == tenant_id,
    )
    return db.scalar(statement)


def get_by_id_for_update(
    db: Session,
    job_id: uuid.UUID,
):
    statement = (
        select(BackgroundJob)
        .where(BackgroundJob.id == job_id)
        .with_for_update()
    )
    return db.scalar(statement)


def mark_job_running(
    db: Session,
    job_id: uuid.UUID,
) -> BackgroundJob:

    job = get_by_id_for_update(db, job_id)

    if job is None:
        raise LookupError("Background job does not exist.")

    if job.status in ("succeeded", "failed"):
        return job

    job.status = "running"

    if job.started_at is None:
        job.started_at = datetime.now(timezone.utc)

    db.flush()
    return job


def mark_job_succeeded(
    db: Session,
    *,
    job_id: uuid.UUID,
    result: dict,
) -> BackgroundJob:

    job = get_by_id_for_update(db, job_id)

    if job is None:
        raise LookupError("Background job does not exist.")

    if job.status == "succeeded":
        return job

    if job.status == "failed":
        raise RuntimeError("Failed job cannot become succeeded.")

    job.status = "succeeded"
    job.result = result
    job.completed_at = datetime.now(timezone.utc)

    db.flush()
    return job


def mark_job_failed(
    db: Session,
    job_id: uuid.UUID,
) -> BackgroundJob:

    job = get_by_id_for_update(db, job_id)

    if job is None:
        raise LookupError("Background job does not exist.")

    if job.status == "succeeded":
        return job

    job.status = "failed"
    job.completed_at = datetime.now(timezone.utc)

    db.flush()
    return job
