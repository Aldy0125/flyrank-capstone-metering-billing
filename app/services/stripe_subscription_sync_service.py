import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.stripe_event_repository import register_event_if_new
from app.repositories.subscription_repository import (
    get_by_tenant_id_for_update,
    get_by_stripe_customer_id,
    get_by_stripe_subscription_id,
    update_subscription_from_stripe,
)


class StripeSubscriptionSyncError(Exception):
    """Raised when a Stripe event cannot be synchronized safely."""


def _get(value: Any, key: str, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _timestamp(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise StripeSubscriptionSyncError(
            "Stripe subscription contains an invalid period timestamp."
        )


def _is_stale_event(subscription, event_created: datetime) -> bool:
    last_event_created_at = subscription.last_stripe_event_created_at
    return (
        last_event_created_at is not None
        and event_created < last_event_created_at
    )


def _tenant_id_from(metadata, fallback=None):
    raw = _get(metadata, "tenant_id") if metadata else None
    raw = raw or fallback

    if not raw:
        return None

    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        raise StripeSubscriptionSyncError(
            "Stripe event contains an invalid tenant_id."
        )


def _resolve_subscription(db: Session, obj):
    metadata = _get(obj, "metadata")
    tenant_id = _tenant_id_from(
        metadata,
        _get(obj, "client_reference_id"),
    )

    stripe_subscription_id = _get(obj, "subscription")
    stripe_customer_id = _get(obj, "customer")

    if stripe_subscription_id:
        existing = get_by_stripe_subscription_id(
            db, str(stripe_subscription_id)
        )
        if existing:
            return get_by_tenant_id_for_update(db, existing.tenant_id)

    if stripe_customer_id:
        existing = get_by_stripe_customer_id(
            db, str(stripe_customer_id)
        )
        if existing:
            return get_by_tenant_id_for_update(db, existing.tenant_id)

    if tenant_id:
        return get_by_tenant_id_for_update(db, tenant_id)

    raise StripeSubscriptionSyncError(
        "Unable to identify the tenant for this Stripe event."
    )


def process_stripe_event(
    db: Session,
    *,
    event,
) -> dict:
    event_id = _get(event, "id")
    event_type = _get(event, "type")
    event_created = _get(event, "created")

    if not event_id or not event_type or event_created is None:
        raise StripeSubscriptionSyncError(
            "Stripe event is missing required identifiers."
        )

    created_at = datetime.fromtimestamp(
        int(event_created),
        tz=timezone.utc,
    )

    # Event registration and subscription synchronization
    # must commit or roll back as one database transaction.
    transaction_scope = (
        db.begin() if not db.in_transaction() else nullcontext()
    )

    with transaction_scope:
        is_new = register_event_if_new(
            db,
            stripe_event_id=str(event_id),
            event_type=str(event_type),
            created_at=created_at,
        )

        if not is_new:
            return {
                "received": True,
                "duplicate": True,
                "event_id": str(event_id),
            }

        obj = _get(_get(event, "data"), "object")

        if event_type == "checkout.session.completed":
            if _get(obj, "mode") != "subscription":
                return {
                    "received": True,
                    "ignored": True,
                    "reason": "Not a subscription checkout.",
                    "event_id": str(event_id),
                }

            stripe_subscription_id = _get(obj, "subscription")
            stripe_customer_id = _get(obj, "customer")
            metadata = _get(obj, "metadata")

            tenant_id = _tenant_id_from(
                metadata,
                _get(obj, "client_reference_id"),
            )

            if not tenant_id or not stripe_subscription_id:
                raise StripeSubscriptionSyncError(
                    "Checkout event is missing tenant or subscription metadata."
                )

            subscription = get_by_tenant_id_for_update(
                db, tenant_id
            )

            if subscription is None:
                raise StripeSubscriptionSyncError(
                    "Tenant subscription does not exist."
                )

            if _is_stale_event(subscription, created_at):
                return {
                    "received": True,
                    "duplicate": False,
                    "stale": True,
                    "event_id": str(event_id),
                    "event_type": str(event_type),
                }

            update_subscription_from_stripe(
                db,
                subscription=subscription,
                plan_id="pro",
                status="active",
                stripe_customer_id=(
                    str(stripe_customer_id) if stripe_customer_id else None
                ),
                stripe_subscription_id=str(stripe_subscription_id),
            )
            subscription.last_stripe_event_created_at = created_at
            db.flush()

        elif event_type in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            subscription = _resolve_subscription(db, obj)

            if _is_stale_event(subscription, created_at):
                return {
                    "received": True,
                    "duplicate": False,
                    "stale": True,
                    "event_id": str(event_id),
                    "event_type": str(event_type),
                }

            stripe_status = (
                "canceled"
                if event_type == "customer.subscription.deleted"
                else str(_get(obj, "status", "unknown"))
            )

            plan_id = (
                "pro"
                if stripe_status in ("active", "trialing")
                else "free"
            )

            update_subscription_from_stripe(
                db,
                subscription=subscription,
                plan_id=plan_id,
                status=stripe_status,
                stripe_customer_id=(
                    str(_get(obj, "customer"))
                    if _get(obj, "customer") else None
                ),
                stripe_subscription_id=(
                    str(_get(obj, "id"))
                    if _get(obj, "id") else None
                ),
                current_period_start=_timestamp(
                    _get(obj, "current_period_start")
                ),
                current_period_end=_timestamp(
                    _get(obj, "current_period_end")
                ),
            )
            subscription.last_stripe_event_created_at = created_at
            db.flush()

        return {
            "received": True,
            "duplicate": False,
            "event_id": str(event_id),
            "event_type": str(event_type),
        }
