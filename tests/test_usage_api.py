import uuid

from datetime import datetime, timezone

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.api.deps import get_db
from app.config.database import SessionLocal

from app.models.tenant import Tenant
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.idempotency import IdempotencyRecord
from app.models.usage_event import UsageEvent

from app.services.usage_metering_service import (
    get_utc_billing_period,
)


@pytest.fixture
def client():
    """
    Use real PostgreSQL sessions for HTTP requests.
    """

    def override_get_db():
        db = SessionLocal()

        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def tenant_factory():
    """
    Create committed test tenants and clean them afterward.
    """

    tenant_ids = []

    def create_tenant(
        *,
        plan_id="free",
        status="active",
    ):
        tenant_id = uuid.uuid4()

        with SessionLocal.begin() as db:
            plan = db.get(Plan, plan_id)

            assert plan is not None

            tenant = Tenant(
                id=tenant_id,
                name=f"Usage API Tenant {tenant_id}",
            )

            db.add(tenant)
            db.flush()

            subscription = Subscription(
                tenant_id=tenant_id,
                plan_id=plan.id,
                status=status,
            )

            db.add(subscription)

        tenant_ids.append(tenant_id)

        return tenant_id

    yield create_tenant

    for tenant_id in tenant_ids:
        with SessionLocal.begin() as db:
            db.execute(
                delete(UsageEvent).where(
                    UsageEvent.tenant_id == tenant_id
                )
            )

            db.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.tenant_id == tenant_id
                )
            )

            db.execute(
                delete(Subscription).where(
                    Subscription.tenant_id == tenant_id
                )
            )

            db.execute(
                delete(Tenant).where(
                    Tenant.id == tenant_id
                )
            )


def _create_usage_event(
    *,
    tenant_id,
    api_calls=2,
    input_tokens=100,
    cached_input_tokens=20,
    output_tokens=50,
    reasoning_tokens=10,
    cost_micro_usd=2_580,
):
    period_start, _ = get_utc_billing_period()

    with SessionLocal.begin() as db:
        record = IdempotencyRecord(
            tenant_id=tenant_id,
            idempotency_key=f"usage-api-{uuid.uuid4()}",
            request_hash="a" * 64,
            response_status=200,
            response_body={"success": True},
        )

        db.add(record)
        db.flush()

        event = UsageEvent(
            tenant_id=tenant_id,
            idempotency_record_id=record.id,
            api_calls=api_calls,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cost_micro_usd=cost_micro_usd,
            period_start=period_start,
        )

        db.add(event)


def test_get_usage_returns_http_200(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory()

    response = client.get(
        "/v1/usage",
        headers={
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["plan_id"] == "free"
    assert body["subscription_status"] == "active"

    assert body["api_calls_used"] == 0
    assert body["api_calls_remaining"] == 1_000
    assert body["monthly_api_call_limit"] == 1_000

    assert body["ai_tokens_used"] == 0
    assert body["ai_tokens_remaining"] == 100_000
    assert body["monthly_ai_token_limit"] == 100_000

    assert body["accumulated_cost_micro_usd"] == 0


def test_get_usage_aggregates_postgresql_records(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory()

    _create_usage_event(
        tenant_id=tenant_id,
    )

    response = client.get(
        "/v1/usage",
        headers={
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["api_calls_used"] == 2
    assert body["api_calls_remaining"] == 998

    assert body["ai_tokens_used"] == 150
    assert body["ai_tokens_remaining"] == 99_850

    assert body["accumulated_cost_micro_usd"] == 2_580


def test_get_usage_returns_http_200_for_inactive_subscription(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory(
        status="past_due",
    )

    response = client.get(
        "/v1/usage",
        headers={
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 200
    assert response.json()["subscription_status"] == "past_due"


def test_get_usage_returns_http_404_for_unknown_tenant(client):
    response = client.get(
        "/v1/usage",
        headers={
            "X-Tenant-ID": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 404


def test_get_usage_returns_http_422_without_tenant_header(client):
    response = client.get("/v1/usage")

    assert response.status_code == 422


def test_get_usage_returns_http_422_for_invalid_tenant_uuid(client):
    response = client.get(
        "/v1/usage",
        headers={
            "X-Tenant-ID": "invalid-uuid",
        },
    )

    assert response.status_code == 422


def test_get_usage_returns_http_404_without_subscription(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory()

    with SessionLocal.begin() as db:
        db.execute(
            delete(Subscription).where(
                Subscription.tenant_id == tenant_id
            )
        )

    response = client.get(
        "/v1/usage",
        headers={
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 404
