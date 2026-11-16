from datetime import date

from app.models.idempotency import IdempotencyRecord
from app.models.tenant import Tenant

from app.repositories.usage_repository import (
    create,
    get_monthly_usage,
)


BILLING_PERIOD = date(2026, 11, 1)


def _create_tenant(db_session, name):
    tenant = Tenant(name=name)

    db_session.add(tenant)
    db_session.flush()

    return tenant


def _create_usage_event(
    db_session,
    *,
    tenant_id,
    key,
    period_start,
    api_calls=1,
    input_tokens=100,
    cached_input_tokens=20,
    output_tokens=50,
    reasoning_tokens=10,
    cost_micro_usd=100_000,
):
    idempotency_record = IdempotencyRecord(
        tenant_id=tenant_id,
        idempotency_key=key,
        request_hash="a" * 64,
        response_status=200,
        response_body={"success": True},
    )

    db_session.add(idempotency_record)
    db_session.flush()

    return create(
        db_session,
        tenant_id=tenant_id,
        idempotency_record_id=idempotency_record.id,
        api_calls=api_calls,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_micro_usd=cost_micro_usd,
        period_start=period_start,
    )


def test_empty_monthly_usage_returns_zero(db_session):
    tenant = _create_tenant(db_session, "Empty Tenant")

    result = get_monthly_usage(
        db_session,
        tenant_id=tenant.id,
        period_start=BILLING_PERIOD,
    )

    assert result == {
        "api_calls": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "ai_tokens_used": 0,
        "cost_micro_usd": 0,
    }


def test_single_usage_event_aggregation(db_session):
    tenant = _create_tenant(db_session, "Single Event Tenant")

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="single-event",
        period_start=BILLING_PERIOD,
        api_calls=2,
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=50,
        reasoning_tokens=10,
        cost_micro_usd=123_456,
    )

    result = get_monthly_usage(
        db_session,
        tenant_id=tenant.id,
        period_start=BILLING_PERIOD,
    )

    assert result["api_calls"] == 2
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50
    assert result["ai_tokens_used"] == 150
    assert result["cost_micro_usd"] == 123_456


def test_multiple_usage_events_are_aggregated(db_session):
    tenant = _create_tenant(db_session, "Multiple Events Tenant")

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="event-one",
        period_start=BILLING_PERIOD,
        api_calls=1,
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=50,
        reasoning_tokens=10,
        cost_micro_usd=100_000,
    )

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="event-two",
        period_start=BILLING_PERIOD,
        api_calls=2,
        input_tokens=200,
        cached_input_tokens=30,
        output_tokens=100,
        reasoning_tokens=20,
        cost_micro_usd=250_000,
    )

    result = get_monthly_usage(
        db_session,
        tenant_id=tenant.id,
        period_start=BILLING_PERIOD,
    )

    assert result["api_calls"] == 3
    assert result["input_tokens"] == 300
    assert result["cached_input_tokens"] == 50
    assert result["output_tokens"] == 150
    assert result["reasoning_tokens"] == 30
    assert result["ai_tokens_used"] == 450
    assert result["cost_micro_usd"] == 350_000


def test_cached_input_tokens_are_not_double_counted(db_session):
    tenant = _create_tenant(db_session, "Cached Token Tenant")

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="cached-token",
        period_start=BILLING_PERIOD,
        input_tokens=120,
        cached_input_tokens=40,
        output_tokens=80,
        reasoning_tokens=0,
    )

    result = get_monthly_usage(
        db_session,
        tenant_id=tenant.id,
        period_start=BILLING_PERIOD,
    )

    assert result["input_tokens"] == 120
    assert result["cached_input_tokens"] == 40
    assert result["ai_tokens_used"] == 200


def test_reasoning_tokens_are_not_double_counted(db_session):
    tenant = _create_tenant(db_session, "Reasoning Token Tenant")

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="reasoning-token",
        period_start=BILLING_PERIOD,
        input_tokens=100,
        cached_input_tokens=0,
        output_tokens=80,
        reasoning_tokens=25,
    )

    result = get_monthly_usage(
        db_session,
        tenant_id=tenant.id,
        period_start=BILLING_PERIOD,
    )

    assert result["output_tokens"] == 80
    assert result["reasoning_tokens"] == 25
    assert result["ai_tokens_used"] == 180


def test_tenant_usage_isolation(db_session):
    tenant_a = _create_tenant(db_session, "Tenant A")
    tenant_b = _create_tenant(db_session, "Tenant B")

    _create_usage_event(
        db_session,
        tenant_id=tenant_a.id,
        key="tenant-a-event",
        period_start=BILLING_PERIOD,
        api_calls=2,
        input_tokens=100,
        output_tokens=50,
        cost_micro_usd=1_000,
    )

    _create_usage_event(
        db_session,
        tenant_id=tenant_b.id,
        key="tenant-b-event",
        period_start=BILLING_PERIOD,
        api_calls=9,
        input_tokens=900,
        output_tokens=300,
        cost_micro_usd=9_000,
    )

    result = get_monthly_usage(
        db_session,
        tenant_id=tenant_a.id,
        period_start=BILLING_PERIOD,
    )

    assert result["api_calls"] == 2
    assert result["input_tokens"] == 100
    assert result["ai_tokens_used"] == 150
    assert result["cost_micro_usd"] == 1_000


def test_billing_period_isolation(db_session):
    tenant = _create_tenant(db_session, "Period Isolation Tenant")

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="november-event",
        period_start=date(2026, 11, 1),
        api_calls=2,
        input_tokens=100,
        output_tokens=50,
        cost_micro_usd=100_000,
    )

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="october-event",
        period_start=date(2026, 10, 1),
        api_calls=5,
        input_tokens=500,
        output_tokens=200,
        cost_micro_usd=500_000,
    )

    result = get_monthly_usage(
        db_session,
        tenant_id=tenant.id,
        period_start=date(2026, 11, 1),
    )

    assert result["api_calls"] == 2
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50
    assert result["cost_micro_usd"] == 100_000


def test_cost_accumulation_uses_integer_arithmetic(db_session):
    tenant = _create_tenant(db_session, "Cost Precision Tenant")

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="cost-event-one",
        period_start=BILLING_PERIOD,
        cost_micro_usd=123_456_789,
    )

    _create_usage_event(
        db_session,
        tenant_id=tenant.id,
        key="cost-event-two",
        period_start=BILLING_PERIOD,
        cost_micro_usd=987_654_321,
    )

    result = get_monthly_usage(
        db_session,
        tenant_id=tenant.id,
        period_start=BILLING_PERIOD,
    )

    assert result["cost_micro_usd"] == 1_111_111_110
    assert isinstance(result["cost_micro_usd"], int)
