import uuid
from datetime import date

from sqlalchemy import select, func

from app.models.tenant import Tenant
from app.models.background_job import BackgroundJob
from app.models.job_failure import JobFailure

from app.repositories.background_job_repository import (
    create_usage_report_job,
    mark_job_running,
    mark_job_succeeded,
    mark_job_failed,
    get_by_id_for_tenant,
)

from app.repositories.job_failure_repository import record_failure

from app.services.usage_report_service import generate_usage_report


def create_tenant(db_session):
    tenant = Tenant(name=f"Background Test {uuid.uuid4()}")
    db_session.add(tenant)
    db_session.flush()
    return tenant


def test_usage_report_job_lifecycle(db_session):
    tenant = create_tenant(db_session)

    job = create_usage_report_job(
        db_session,
        tenant_id=tenant.id,
        period_start=date(2026, 11, 1),
    )

    assert job.status == "queued"

    mark_job_running(db_session, job.id)
    db_session.refresh(job)

    assert job.status == "running"
    assert job.started_at is not None

    result = {
        "report_type": "monthly_usage",
        "api_calls": 10,
    }

    mark_job_succeeded(
        db_session,
        job_id=job.id,
        result=result,
    )

    db_session.refresh(job)

    assert job.status == "succeeded"
    assert job.result == result
    assert job.completed_at is not None


def test_usage_report_returns_monthly_aggregates(db_session):
    tenant = create_tenant(db_session)

    report = generate_usage_report(
        db_session,
        tenant_id=tenant.id,
        period_start=date(2026, 11, 1),
    )

    assert report["report_type"] == "monthly_usage"
    assert report["period_start"] == "2026-11-01"
    assert report["period_end"] == "2026-11-30"
    assert report["api_calls"] == 0
    assert report["ai_tokens_used"] == 0
    assert report["cost_micro_usd"] == 0


def test_usage_report_rejects_invalid_period_start(db_session):
    tenant = create_tenant(db_session)

    try:
        generate_usage_report(
            db_session,
            tenant_id=tenant.id,
            period_start=date(2026, 11, 15),
        )
    except ValueError as exc:
        assert "first day" in str(exc)
    else:
        raise AssertionError("Invalid billing period was accepted.")


def test_job_failure_recording_is_idempotent(db_session):
    first = record_failure(
        db_session,
        function_id="generate-usage-report",
        job_id="job-test-001",
        error_message="Temporary test failure",
    )

    second = record_failure(
        db_session,
        function_id="generate-usage-report",
        job_id="job-test-001",
        error_message="Duplicate failure",
    )

    assert first.id == second.id

    count = db_session.scalar(
        select(func.count())
        .select_from(JobFailure)
        .where(JobFailure.job_id == "job-test-001")
    )

    assert count == 1


def test_failed_job_cannot_be_marked_succeeded(db_session):
    tenant = create_tenant(db_session)

    job = create_usage_report_job(
        db_session,
        tenant_id=tenant.id,
        period_start=date(2026, 11, 1),
    )

    mark_job_failed(db_session, job.id)

    try:
        mark_job_succeeded(
            db_session,
            job_id=job.id,
            result={"api_calls": 0},
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Failed job was incorrectly completed.")

    db_session.refresh(job)
    assert job.status == "failed"


def test_job_is_scoped_to_tenant(db_session):
    tenant_a = create_tenant(db_session)
    tenant_b = create_tenant(db_session)

    job = create_usage_report_job(
        db_session,
        tenant_id=tenant_a.id,
        period_start=date(2026, 11, 1),
    )

    assert get_by_id_for_tenant(
        db_session,
        job_id=job.id,
        tenant_id=tenant_a.id,
    ) is not None

    assert get_by_id_for_tenant(
        db_session,
        job_id=job.id,
        tenant_id=tenant_b.id,
    ) is None
