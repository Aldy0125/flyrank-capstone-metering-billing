"""
Usage summary service.

Provides read-only monthly usage information
for a tenant based on its current subscription plan.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.schemas.usage import UsageResponse

from app.repositories.tenant_repository import (
    get_by_id as get_tenant_by_id,
)

from app.repositories.subscription_repository import (
    get_by_tenant_id as get_subscription_by_tenant_id,
)

from app.repositories.plan_repository import (
    get_by_id as get_plan_by_id,
)

from app.repositories.usage_repository import (
    get_monthly_usage,
)

from app.services.usage_metering_service import (
    get_utc_billing_period,
    TenantNotFoundError,
    SubscriptionNotFoundError,
    PlanNotFoundError,
)


def get_usage_summary(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    now: datetime | None = None,
) -> UsageResponse:
    """
    Retrieve a tenant's monthly usage summary.

    Inactive subscriptions remain reportable.
    This function does not modify database records.
    """

    tenant = get_tenant_by_id(
        db,
        tenant_id,
    )

    if tenant is None:
        raise TenantNotFoundError(
            f"Tenant '{tenant_id}' does not exist."
        )

    subscription = get_subscription_by_tenant_id(
        db,
        tenant_id,
    )

    if subscription is None:
        raise SubscriptionNotFoundError(
            f"Tenant '{tenant_id}' has no subscription."
        )

    plan = get_plan_by_id(
        db,
        subscription.plan_id,
    )

    if plan is None:
        raise PlanNotFoundError(
            f"Plan '{subscription.plan_id}' does not exist."
        )

    period_start, period_end = get_utc_billing_period(
        now
    )

    usage = get_monthly_usage(
        db,
        tenant_id=tenant_id,
        period_start=period_start,
    )

    api_calls_remaining = max(
        0,
        plan.api_call_limit - usage["api_calls"],
    )

    ai_tokens_remaining = max(
        0,
        plan.ai_token_limit - usage["ai_tokens_used"],
    )

    return UsageResponse(
        plan_id=plan.id,
        subscription_status=subscription.status,

        api_calls_used=usage["api_calls"],
        api_calls_remaining=api_calls_remaining,
        monthly_api_call_limit=plan.api_call_limit,

        ai_tokens_used=usage["ai_tokens_used"],
        ai_tokens_remaining=ai_tokens_remaining,
        monthly_ai_token_limit=plan.ai_token_limit,

        accumulated_cost_micro_usd=usage["cost_micro_usd"],

        billing_period_start=period_start,
        billing_period_end=period_end,
    )
