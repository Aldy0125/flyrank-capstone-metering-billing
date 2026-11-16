from datetime import date, datetime, timezone
import uuid

import pytest

from sqlalchemy import func, select

from app.models.tenant import Tenant
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.idempotency import IdempotencyRecord
from app.models.usage_event import UsageEvent

from app.schemas.usage import GenerateRequest

from app.services.usage_metering_service import (
    meter_usage_request,
    MeteringResult,
    TenantNotFoundError,
    IdempotencyConflictError,
)


BILLING_START = date(2026, 11, 1)

TEST_NOW = datetime(
    2026, 11, 16, 12, 0,
    tzinfo=timezone.utc,
)


def _create_tenant(
    db_session,
    *,
    plan_id="free",
    status="active",
):
    plan = db_session.get(Plan, plan_id)

    assert plan is not None, (
        f"Seeded plan '{plan_id}' does not exist."
    )

    tenant = Tenant(
        name=f"Atomic Test Tenant {uuid.uuid4()}",
    )

    db_session.add(tenant)
    db_session.flush()

    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=status,
    )

    db_session.add(subscription)
    db_session.flush()

    return tenant


def _create_request(
    *,
    input_tokens=100,
    cached_input_tokens=20,
    output_tokens=50,
    reasoning_tokens=10,
):
    return GenerateRequest(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _create_prior_usage(
    db_session,
    *,
    tenant_id,
    api_calls=0,
    input_tokens=0,
    output_tokens=0,
):
    record = IdempotencyRecord(
        tenant_id=tenant_id,
        idempotency_key=f"prior-{uuid.uuid4()}",
        request_hash="a" * 64,
        response_status=200,
        response_body={"success": True},
    )

    db_session.add(record)
    db_session.flush()

    event = UsageEvent(
        tenant_id=tenant_id,
        idempotency_record_id=record.id,
        api_calls=api_calls,
        input_tokens=input_tokens,
        cached_input_tokens=0,
        output_tokens=output_tokens,
        reasoning_tokens=0,
        cost_micro_usd=0,
        period_start=BILLING_START,
    )

    db_session.add(event)
    db_session.flush()

    return event


def _count_records(
    db_session,
    model,
    tenant_id,
):
    statement = (
        select(func.count())
        .select_from(model)
        .where(model.tenant_id == tenant_id)
    )

    return db_session.scalar(statement)


def _meter(
    db_session,
    *,
    tenant_id,
    key,
    request=None,
):
    if request is None:
        request = _create_request()

    return meter_usage_request(
        db_session,
        tenant_id=tenant_id,
        idempotency_key=key,
        request=request,
        now=TEST_NOW,
    )


def test_successful_metering_creates_one_usage_event(db_session):
    tenant = _create_tenant(db_session)

    request = _create_request()

    result = _meter(
        db_session,
        tenant_id=tenant.id,
        key="success-key",
        request=request,
    )

    assert isinstance(result, MeteringResult)
    assert result.status_code == 200
    assert result.body["success"] is True
    assert result.body["usage"]["api_calls"] == 1
    assert result.body["usage"]["ai_tokens_used"] == 150
    assert result.body["usage"]["cost_micro_usd"] == 1_580

    assert _count_records(
        db_session,
        UsageEvent,
        tenant.id,
    ) == 1

    assert _count_records(
        db_session,
        IdempotencyRecord,
        tenant.id,
    ) == 1


def test_same_key_same_payload_returns_original_response(db_session):
    tenant = _create_tenant(db_session)

    request = _create_request()

    first = _meter(
        db_session,
        tenant_id=tenant.id,
        key="replay-key",
        request=request,
    )

    second = _meter(
        db_session,
        tenant_id=tenant.id,
        key="replay-key",
        request=request,
    )

    assert first.status_code == 200
    assert second.status_code == first.status_code
    assert second.body == first.body
    assert second.replayed is True

    assert _count_records(
        db_session,
        UsageEvent,
        tenant.id,
    ) == 1

    assert _count_records(
        db_session,
        IdempotencyRecord,
        tenant.id,
    ) == 1


def test_same_key_different_payload_returns_conflict(db_session):
    tenant = _create_tenant(db_session)

    _meter(
        db_session,
        tenant_id=tenant.id,
        key="conflict-key",
        request=_create_request(input_tokens=100),
    )

    with pytest.raises(IdempotencyConflictError):
        _meter(
            db_session,
            tenant_id=tenant.id,
            key="conflict-key",
            request=_create_request(input_tokens=200),
        )

    assert _count_records(
        db_session,
        UsageEvent,
        tenant.id,
    ) == 1


def test_free_api_quota_exhaustion_returns_402(db_session):
    tenant = _create_tenant(db_session)

    _create_prior_usage(
        db_session,
        tenant_id=tenant.id,
        api_calls=1_000,
    )

    result = _meter(
        db_session,
        tenant_id=tenant.id,
        key="free-api-quota",
        request=_create_request(
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        ),
    )

    assert result.status_code == 402
    assert result.body["code"] == "quota_exceeded"

    assert _count_records(
        db_session,
        UsageEvent,
        tenant.id,
    ) == 1

    assert _count_records(
        db_session,
        IdempotencyRecord,
        tenant.id,
    ) == 2


def test_pro_api_quota_exhaustion_returns_429(db_session):
    tenant = _create_tenant(
        db_session,
        plan_id="pro",
    )

    _create_prior_usage(
        db_session,
        tenant_id=tenant.id,
        api_calls=10_000,
    )

    result = _meter(
        db_session,
        tenant_id=tenant.id,
        key="pro-api-quota",
        request=_create_request(
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        ),
    )

    assert result.status_code == 429
    assert result.body["code"] == "quota_exceeded"
    assert result.body["retry_after_seconds"] > 0

    assert _count_records(
        db_session,
        UsageEvent,
        tenant.id,
    ) == 1


def test_exact_ai_token_quota_is_allowed(db_session):
    tenant = _create_tenant(db_session)

    _create_prior_usage(
        db_session,
        tenant_id=tenant.id,
        input_tokens=99_900,
    )

    result = _meter(
        db_session,
        tenant_id=tenant.id,
        key="exact-token-quota",
        request=_create_request(
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        ),
    )

    assert result.status_code == 200
    assert result.body["usage"]["ai_tokens_used"] == 100


def test_exceeding_ai_token_quota_is_rejected(db_session):
    tenant = _create_tenant(db_session)

    _create_prior_usage(
        db_session,
        tenant_id=tenant.id,
        input_tokens=100_000,
    )

    result = _meter(
        db_session,
        tenant_id=tenant.id,
        key="exceed-token-quota",
        request=_create_request(
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        ),
    )

    assert result.status_code == 402
    assert result.body["code"] == "quota_exceeded"

    assert _count_records(
        db_session,
        UsageEvent,
        tenant.id,
    ) == 1


def test_inactive_subscription_returns_402_without_usage(db_session):
    tenant = _create_tenant(
        db_session,
        status="past_due",
    )

    result = _meter(
        db_session,
        tenant_id=tenant.id,
        key="inactive-subscription",
    )

    assert result.status_code == 402
    assert result.body["code"] == "subscription_not_active"

    assert _count_records(
        db_session,
        UsageEvent,
        tenant.id,
    ) == 0

    assert _count_records(
        db_session,
        IdempotencyRecord,
        tenant.id,
    ) == 1


def test_unknown_tenant_is_rejected(db_session):
    with pytest.raises(TenantNotFoundError):
        _meter(
            db_session,
            tenant_id=uuid.uuid4(),
            key="unknown-tenant",
        )


def test_same_idempotency_key_allowed_for_different_tenants(db_session):
    tenant_a = _create_tenant(db_session)
    tenant_b = _create_tenant(db_session)

    result_a = _meter(
        db_session,
        tenant_id=tenant_a.id,
        key="shared-key",
    )

    result_b = _meter(
        db_session,
        tenant_id=tenant_b.id,
        key="shared-key",
    )

    assert result_a.status_code == 200
    assert result_b.status_code == 200

    assert _count_records(
        db_session,
        UsageEvent,
        tenant_a.id,
    ) == 1

    assert _count_records(
        db_session,
        UsageEvent,
        tenant_b.id,
    ) == 1


def test_quota_rejection_is_idempotent(db_session):
    tenant = _create_tenant(db_session)

    _create_prior_usage(
        db_session,
        tenant_id=tenant.id,
        api_calls=1_000,
    )

    request = _create_request(
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
    )

    first = _meter(
        db_session,
        tenant_id=tenant.id,
        key="rejected-replay",
        request=request,
    )

    second = _meter(
        db_session,
        tenant_id=tenant.id,
        key="rejected-replay",
        request=request,
    )

    assert first.status_code == 402
    assert second.status_code == 402
    assert second.replayed is True
    assert second.body == first.body

    assert _count_records(
        db_session,
        UsageEvent,
        tenant.id,
    ) == 1


def test_exact_api_call_quota_is_allowed(db_session):
    tenant = _create_tenant(db_session)

    _create_prior_usage(
        db_session,
        tenant_id=tenant.id,
        api_calls=999,
    )

    result = _meter(
        db_session,
        tenant_id=tenant.id,
        key="exact-api-quota",
        request=_create_request(
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        ),
    )

    assert result.status_code == 200
    assert result.body["usage"]["api_calls"] == 1
