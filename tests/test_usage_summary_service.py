from datetime import date, datetime, timezone
import uuid

import pytest

from app.models.tenant import Tenant
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.idempotency import IdempotencyRecord
from app.models.usage_event import UsageEvent

from app.services.usage_summary_service import (
    get_usage_summary,
)

from app.services.usage_metering_service import (
    TenantNotFoundError,
    SubscriptionNotFoundError,
)


TEST_NOW = datetime(
    2026, 11, 16, 12, 0,
    tzinfo=timezone.utc,
)

BILLING_START = date(2026, 11, 1)


def _create_tenant_subscription(
    db_session,
    *,
    plan_id="free",
    status="active",
):
    plan = db_session.get(Plan, plan_id)

    assert plan is not None

    tenant = Tenant(
        name=f"Summary Tenant {uuid.uuid4()}",
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


def _create_usage_event(
    db_session,
    *,
    tenant_id,
    api_calls,
    input_tokens,
    cached_input_tokens,
    output_tokens,
    reasoning_tokens,
    cost_micro_usd,
):
    record = IdempotencyRecord(
        tenant_id=tenant_id,
        idempotency_key=f"summary-{uuid.uuid4()}",
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
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_micro_usd=cost_micro_usd,
        period_start=BILLING_START,
    )

    db_session.add(event)
    db_session.flush()

    return event


def test_empty_usage_summary_returns_zero(db_session):
    tenant = _create_tenant_subscription(db_session)

    result = get_usage_summary(
        db_session,
        tenant_id=tenant.id,
        now=TEST_NOW,
    )

    assert result.plan_id == "free"
    assert result.subscription_status == "active"

    assert result.api_calls_used == 0
    assert result.api_calls_remaining == 1_000

    assert result.ai_tokens_used == 0
    assert result.ai_tokens_remaining == 100_000

    assert result.accumulated_cost_micro_usd == 0

    assert result.billing_period_start == BILLING_START
    assert result.billing_period_end == date(2026, 11, 30)


def test_usage_summary_aggregates_existing_events(db_session):
    tenant = _create_tenant_subscription(db_session)

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        api_calls=2,
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=50,
        reasoning_tokens=10,
        cost_micro_usd=2_580,
    )

    result = get_usage_summary(
        db_session,
        tenant_id=tenant.id,
        now=TEST_NOW,
    )

    assert result.api_calls_used == 2
    assert result.api_calls_remaining == 998

    assert result.ai_tokens_used == 150
    assert result.ai_tokens_remaining == 99_850

    assert result.accumulated_cost_micro_usd == 2_580


def test_usage_summary_reports_inactive_subscription(db_session):
    tenant = _create_tenant_subscription(
        db_session,
        status="past_due",
    )

    result = get_usage_summary(
        db_session,
        tenant_id=tenant.id,
        now=TEST_NOW,
    )

    assert result.subscription_status == "past_due"
    assert result.plan_id == "free"


def test_usage_summary_handles_usage_above_downgraded_plan_limit(
    db_session,
):
    tenant = _create_tenant_subscription(
        db_session,
        plan_id="free",
    )

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        api_calls=1_100,
        input_tokens=110_000,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        cost_micro_usd=0,
    )

    result = get_usage_summary(
        db_session,
        tenant_id=tenant.id,
        now=TEST_NOW,
    )

    assert result.api_calls_used == 1_100
    assert result.api_calls_remaining == 0

    assert result.ai_tokens_used == 110_000
    assert result.ai_tokens_remaining == 0


def test_unknown_tenant_is_rejected(db_session):
    with pytest.raises(TenantNotFoundError):
        get_usage_summary(
            db_session,
            tenant_id=uuid.uuid4(),
            now=TEST_NOW,
        )


def test_tenant_without_subscription_is_rejected(db_session):
    tenant = Tenant(
        name="Tenant Without Subscription",
    )

    db_session.add(tenant)
    db_session.flush()

    with pytest.raises(SubscriptionNotFoundError):
        get_usage_summary(
            db_session,
            tenant_id=tenant.id,
            now=TEST_NOW,
        )
