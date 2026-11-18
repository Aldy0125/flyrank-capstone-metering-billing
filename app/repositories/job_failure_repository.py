import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job_failure import JobFailure


def record_failure(
    db: Session,
    *,
    function_id: str,
    job_id: str,
    error_message: str,
) -> JobFailure:

    existing = db.scalar(
        select(JobFailure).where(
            JobFailure.function_id == function_id,
            JobFailure.job_id == job_id,
        )
    )

    if existing is not None:
        return existing

    failure = JobFailure(
        id=uuid.uuid4(),
        function_id=function_id,
        job_id=job_id,
        error_message=error_message[:10000],
        failed_at=datetime.now(timezone.utc),
    )

    db.add(failure)
    db.flush()

    return failure
