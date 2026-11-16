import uuid

import pytest

from app.models.tenant import Tenant
from app.models.plan import Plan
from app.models.subscription import Subscription

from app.services.usage_metering_service import (
    get_active_subscription_context,
    TenantNotFoundError,
    SubscriptionNotFoundError,
    SubscriptionNotActiveError,
    PlanInactiveError,
)


def _create_subscription_context(
    db_session,
    *,
    plan_id="free",
    status="active",
    plan_active=None,
):
    """
    Create a tenant and subscription using an existing seeded plan.

    The existing Free and Pro plan records are reused.
    No duplicate plan records are inserted.
    """

    # Retrieve an existing plan from database seeding.
    plan = db_session.get(Plan, plan_id)

    assert plan is not None, (
        f"Seeded plan '{plan_id}' does not exist. "
        "Run the database seed process first."
    )

    # Modify plan availability only when explicitly requested.
    # The test transaction will roll back this modification.
    if plan_active is not None:
        plan.is_active = plan_active
        db_session.flush()

    # Create a unique tenant for each test.
    tenant = Tenant(
        name=f"Test Tenant {uuid.uuid4()}",
    )

    db_session.add(tenant)
    db_session.flush()

    # Create subscription referencing the existing plan.
    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=status,
    )

    db_session.add(subscription)
    db_session.flush()

    return tenant, subscription, plan


def test_active_free_subscription_is_valid(db_session):
    tenant, subscription, plan = _create_subscription_context(
        db_session,
        plan_id="free",
    )

    result_subscription, result_plan = (
        get_active_subscription_context(
            db_session,
            tenant_id=tenant.id,
        )
    )

    assert result_subscription.id == subscription.id
    assert result_plan.id == plan.id
    assert result_plan.api_call_limit == 1_000
    assert result_plan.ai_token_limit == 100_000


def test_active_pro_subscription_is_valid(db_session):
    tenant, subscription, plan = _create_subscription_context(
        db_session,
        plan_id="pro",
    )

    result_subscription, result_plan = (
        get_active_subscription_context(
            db_session,
            tenant_id=tenant.id,
        )
    )

    assert result_subscription.id == subscription.id
    assert result_plan.id == plan.id
    assert result_plan.api_call_limit == 10_000
    assert result_plan.ai_token_limit == 1_000_000


def test_unknown_tenant_is_rejected(db_session):
    unknown_tenant_id = uuid.uuid4()

    with pytest.raises(TenantNotFoundError):
        get_active_subscription_context(
            db_session,
            tenant_id=unknown_tenant_id,
        )


def test_tenant_without_subscription_is_rejected(db_session):
    tenant = Tenant(
        name="Tenant Without Subscription",
    )

    db_session.add(tenant)
    db_session.flush()

    with pytest.raises(SubscriptionNotFoundError):
        get_active_subscription_context(
            db_session,
            tenant_id=tenant.id,
        )


@pytest.mark.parametrize(
    "status",
    [
        "past_due",
        "canceled",
        "incomplete",
    ],
)
def test_non_active_subscription_is_rejected(
    db_session,
    status,
):
    tenant, _, _ = _create_subscription_context(
        db_session,
        status=status,
    )

    with pytest.raises(SubscriptionNotActiveError):
        get_active_subscription_context(
            db_session,
            tenant_id=tenant.id,
        )


def test_inactive_plan_is_rejected(db_session):
    tenant, _, _ = _create_subscription_context(
        db_session,
        plan_active=False,
    )

    with pytest.raises(PlanInactiveError):
        get_active_subscription_context(
            db_session,
            tenant_id=tenant.id,
        )
