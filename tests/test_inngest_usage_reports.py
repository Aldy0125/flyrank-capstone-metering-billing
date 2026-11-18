import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_db
from app.config.database import SessionLocal
from app.models.tenant import Tenant
from app.models.background_job import BackgroundJob
from app.repositories.background_job_repository import (
    create_usage_report_job,
)
from app.integrations.inngest import (
    inngest_client,
    inngest_functions,
)
from app.services.usage_report_worker import (
    complete_usage_report_job,
    persist_usage_report_failure,
)


@pytest.fixture
def usage_report_client(db_session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def create_tenant(db_session):
    tenant = Tenant(name=f"Inngest Test {uuid.uuid4()}")
    db_session.add(tenant)
    db_session.flush()
    return tenant


def test_usage_report_dispatches_inngest_event(
    usage_report_client,
    db_session,
    monkeypatch,
):
    tenant = create_tenant(db_session)
    sent = []

    async def fake_send(event):
        sent.append(event)
        return [event.id]

    monkeypatch.setattr(inngest_client, "send", fake_send)

    response = usage_report_client.post(
        "/v1/usage/reports?period_start=2026-11-01",
        headers={"X-Tenant-ID": str(tenant.id)},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert len(sent) == 1
    assert sent[0].name == "billing/usage-report.requested"
    assert sent[0].data["job_id"] == response.json()["job_id"]

    job = db_session.get(
        BackgroundJob,
        uuid.UUID(response.json()["job_id"]),
    )
    assert job.status == "queued"


def test_usage_report_status_is_tenant_scoped(
    usage_report_client,
    db_session,
    monkeypatch,
):
    tenant_a = create_tenant(db_session)
    tenant_b = create_tenant(db_session)

    job = create_usage_report_job(
        db_session,
        tenant_id=tenant_a.id,
        period_start=date(2026, 11, 1),
    )
    db_session.flush()

    response = usage_report_client.get(
        f"/v1/usage/reports/{job.id}",
        headers={"X-Tenant-ID": str(tenant_b.id)},
    )

    assert response.status_code == 404


def test_usage_report_worker_persists_result(db_session):
    tenant = create_tenant(db_session)

    job = create_usage_report_job(
        db_session,
        tenant_id=tenant.id,
        period_start=date(2026, 11, 1),
    )
    db_session.flush()

    result = complete_usage_report_job(
        db_session,
        str(job.id),
    )

    db_session.refresh(job)

    assert result["report_type"] == "monthly_usage"
    assert job.status == "succeeded"
    assert job.result == result


def test_usage_report_failure_is_persisted(db_session):
    tenant = create_tenant(db_session)

    job = create_usage_report_job(
        db_session,
        tenant_id=tenant.id,
        period_start=date(2026, 11, 1),
    )
    db_session.flush()

    persist_usage_report_failure(
        db_session,
        job_id=str(job.id),
        error_message="Simulated permanent failure",
    )

    db_session.refresh(job)

    assert job.status == "failed"


def test_inngest_function_is_registered():
    assert len(inngest_functions) == 1
    assert inngest_functions[0].id.endswith("-generate-usage-report")
