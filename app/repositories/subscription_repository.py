import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.subscription import Subscription


def get_by_tenant_id(
    db: Session,
    tenant_id: uuid.UUID,
) -> Subscription | None:
    statement = select(Subscription).where(
        Subscription.tenant_id == tenant_id
    )
    return db.scalar(statement)


def get_by_tenant_id_for_update(
    db: Session,
    tenant_id: uuid.UUID,
) -> Subscription | None:
    statement = (
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .with_for_update()
    )
    return db.scalar(statement)


def get_by_stripe_subscription_id(
    db: Session,
    stripe_subscription_id: str,
) -> Subscription | None:
    statement = select(Subscription).where(
        Subscription.stripe_subscription_id == stripe_subscription_id
    )
    return db.scalar(statement)


def get_by_stripe_customer_id(
    db: Session,
    stripe_customer_id: str,
) -> Subscription | None:
    statement = select(Subscription).where(
        Subscription.stripe_customer_id == stripe_customer_id
    )
    return db.scalar(statement)


def update_stripe_customer_id(
    db: Session,
    *,
    subscription: Subscription,
    stripe_customer_id: str,
) -> Subscription:
    subscription.stripe_customer_id = stripe_customer_id
    db.flush()
    db.refresh(subscription)
    return subscription


def update_subscription_from_stripe(
    db: Session,
    *,
    subscription: Subscription,
    plan_id: str,
    status: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    current_period_start: datetime | None = None,
    current_period_end: datetime | None = None,
) -> Subscription:
    subscription.plan_id = plan_id
    subscription.status = status

    if stripe_customer_id:
        subscription.stripe_customer_id = stripe_customer_id

    if stripe_subscription_id:
        subscription.stripe_subscription_id = stripe_subscription_id

    subscription.current_period_start = current_period_start
    subscription.current_period_end = current_period_end

    db.flush()
    return subscription


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
