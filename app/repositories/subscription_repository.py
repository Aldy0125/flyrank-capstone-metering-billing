import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.subscription import Subscription


def get_by_tenant_id(
    db: Session,
    tenant_id: uuid.UUID,
) -> Subscription | None:
    """
    Retrieve a subscription belonging to a tenant.
    """

    statement = select(Subscription).where(
        Subscription.tenant_id == tenant_id
    )

    return db.scalar(statement)


def create(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    plan_id: str,
    status: str,
    current_period_start: datetime | None = None,
    current_period_end: datetime | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> Subscription:
    """
    Create a subscription for a tenant.

    The caller is responsible for committing
    or rolling back the transaction.
    """

    subscription = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_id,
        status=status,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )

    db.add(subscription)
    db.flush()
    db.refresh(subscription)

    return subscription
