import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.usage_event import UsageEvent


def get_monthly_usage(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    period_start: date,
) -> dict[str, int]:
    """
    Retrieve aggregated monthly usage for a tenant.

    Usage is filtered by tenant_id and UTC billing period.
    period_start represents the first day of the billing month.

    Cached input tokens and reasoning tokens are subsets
    of their respective parent token quantities. They are
    aggregated separately and are not double-counted.
    """

    statement = (
        select(
            func.coalesce(
                func.sum(UsageEvent.api_calls), 0
            ).label("api_calls"),
            func.coalesce(
                func.sum(UsageEvent.input_tokens), 0
            ).label("input_tokens"),
            func.coalesce(
                func.sum(UsageEvent.cached_input_tokens), 0
            ).label("cached_input_tokens"),
            func.coalesce(
                func.sum(UsageEvent.output_tokens), 0
            ).label("output_tokens"),
            func.coalesce(
                func.sum(UsageEvent.reasoning_tokens), 0
            ).label("reasoning_tokens"),
            func.coalesce(
                func.sum(UsageEvent.cost_micro_usd), 0
            ).label("cost_micro_usd"),
        )
        .where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.period_start == period_start,
        )
    )

    result = db.execute(statement).one()

    api_calls = int(result.api_calls)
    input_tokens = int(result.input_tokens)
    cached_input_tokens = int(result.cached_input_tokens)
    output_tokens = int(result.output_tokens)
    reasoning_tokens = int(result.reasoning_tokens)
    cost_micro_usd = int(result.cost_micro_usd)

    return {
        "api_calls": api_calls,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "ai_tokens_used": input_tokens + output_tokens,
        "cost_micro_usd": cost_micro_usd,
    }


def create(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    idempotency_record_id: uuid.UUID,
    api_calls: int,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    cost_micro_usd: int,
    period_start: date,
) -> UsageEvent:
    """
    Create a new usage event.

    The caller is responsible for committing
    or rolling back the transaction.
    """

    usage_event = UsageEvent(
        tenant_id=tenant_id,
        idempotency_record_id=idempotency_record_id,
        api_calls=api_calls,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_micro_usd=cost_micro_usd,
        period_start=period_start,
    )

    db.add(usage_event)
    db.flush()
    db.refresh(usage_event)

    return usage_event
