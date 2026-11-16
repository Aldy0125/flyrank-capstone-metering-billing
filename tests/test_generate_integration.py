
import uuid

from datetime import date

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

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
    Create committed tenant fixtures and clean them afterward.
    """

    tenant_ids = []

    def create_tenant(
        *,
        plan_id="free",
        status="active",
        initial_api_calls=0,
    ):
        tenant_id = uuid.uuid4()

        period_start, _ = get_utc_billing_period()

        with SessionLocal.begin() as db:
            plan = db.get(Plan, plan_id)

            assert plan is not None

            tenant = Tenant(
                id=tenant_id,
                name=f"Generate API Tenant {tenant_id}",
            )

            db.add(tenant)
            db.flush()

            subscription = Subscription(
                tenant_id=tenant_id,
                plan_id=plan.id,
                status=status,
            )

            db.add(subscription)
            db.flush()

            if initial_api_calls > 0:
                record = IdempotencyRecord(
                    tenant_id=tenant_id,
                    idempotency_key=f"initial-{uuid.uuid4()}",
                    request_hash="a" * 64,
                    response_status=200,
                    response_body={"success": True},
                )

                db.add(record)
                db.flush()

                event = UsageEvent(
                    tenant_id=tenant_id,
                    idempotency_record_id=record.id,
                    api_calls=initial_api_calls,
                    input_tokens=0,
                    cached_input_tokens=0,
                    output_tokens=0,
                    reasoning_tokens=0,
                    cost_micro_usd=0,
                    period_start=period_start,
                )

                db.add(event)

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


def _headers(
    tenant_id,
    key="generate-integration-key",
):
    return {
        "X-Tenant-ID": str(tenant_id),
        "Idempotency-Key": key,
    }


def _payload(
    *,
    input_tokens=100,
    cached_input_tokens=20,
    output_tokens=50,
    reasoning_tokens=10,
):
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
    }


def _count_records(
    model,
    tenant_id,
):
    with SessionLocal() as db:
        statement = (
            select(func.count())
            .select_from(model)
            .where(model.tenant_id == tenant_id)
        )

        return db.scalar(statement)


def test_generate_creates_usage_event_in_postgresql(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory()

    response = client.post(
        "/v1/generate",
        headers=_headers(tenant_id),
        json=_payload(),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["usage"]["api_calls"] == 1
    assert body["usage"]["ai_tokens_used"] == 150
    assert body["usage"]["cost_micro_usd"] == 1_580

    assert _count_records(
        UsageEvent,
        tenant_id,
    ) == 1

    assert _count_records(
        IdempotencyRecord,
        tenant_id,
    ) == 1


def test_generate_idempotency_replay_through_http(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory()

    headers = _headers(
        tenant_id,
        key="http-replay-key",
    )

    payload = _payload()

    first = client.post(
        "/v1/generate",
        headers=headers,
        json=payload,
    )

    second = client.post(
        "/v1/generate",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    assert second.json() == first.json()

    assert _count_records(
        UsageEvent,
        tenant_id,
    ) == 1

    assert _count_records(
        IdempotencyRecord,
        tenant_id,
    ) == 1


def test_generate_payload_conflict_through_http(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory()

    headers = _headers(
        tenant_id,
        key="http-conflict-key",
    )

    first = client.post(
        "/v1/generate",
        headers=headers,
        json=_payload(input_tokens=100),
    )

    second = client.post(
        "/v1/generate",
        headers=headers,
        json=_payload(input_tokens=200),
    )

    assert first.status_code == 200
    assert second.status_code == 409

    assert _count_records(
        UsageEvent,
        tenant_id,
    ) == 1


def test_free_quota_rejection_through_http(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory(
        initial_api_calls=1_000,
    )

    response = client.post(
        "/v1/generate",
        headers=_headers(
            tenant_id,
            key="http-free-quota",
        ),
        json=_payload(
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        ),
    )

    assert response.status_code == 402
    assert response.json()["code"] == "quota_exceeded"

    # The rejected request must not create another usage event.
    assert _count_records(
        UsageEvent,
        tenant_id,
    ) == 1

    # The original rejection response must be stored.
    assert _count_records(
        IdempotencyRecord,
        tenant_id,
    ) == 2


def test_pro_quota_rejection_through_http(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory(
        plan_id="pro",
        initial_api_calls=10_000,
    )

    response = client.post(
        "/v1/generate",
        headers=_headers(
            tenant_id,
            key="http-pro-quota",
        ),
        json=_payload(
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        ),
    )

    assert response.status_code == 429
    assert response.json()["code"] == "quota_exceeded"

    assert int(response.headers["Retry-After"]) > 0

    assert _count_records(
        UsageEvent,
        tenant_id,
    ) == 1


def test_generate_unknown_tenant_through_http(client):
    response = client.post(
        "/v1/generate",
        headers=_headers(
            uuid.uuid4(),
            key="http-unknown-tenant",
        ),
        json=_payload(),
    )

    assert response.status_code == 404


def test_generate_inactive_subscription_through_http(
    client,
    tenant_factory,
):
    tenant_id = tenant_factory(
        status="past_due",
    )

    response = client.post(
        "/v1/generate",
        headers=_headers(
            tenant_id,
            key="http-inactive-subscription",
        ),
        json=_payload(),
    )

    assert response.status_code == 402

    assert response.json()["code"] == (
        "subscription_not_active"
    )

    assert _count_records(
        UsageEvent,
        tenant_id,
    ) == 0
