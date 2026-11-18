import uuid

from sqlalchemy import select, func

from app.models.plan import Plan
from app.models.tenant import Tenant
from app.models.subscription import Subscription
from app.models.stripe_event import StripeEvent

from app.services.stripe_subscription_sync_service import (
    process_stripe_event,
)


def create_webhook_tenant(db_session, customer_id="cus_webhook_test"):
    assert db_session.get(Plan, "free") is not None
    assert db_session.get(Plan, "pro") is not None

    tenant = Tenant(name=f"Webhook Test {uuid.uuid4()}")
    db_session.add(tenant)
    db_session.flush()

    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id="free",
        status="active",
        stripe_customer_id=customer_id,
    )
    db_session.add(subscription)
    db_session.flush()

    return tenant, subscription


def make_event(event_id, event_type, obj, created=1790000000):
    return {
        "id": event_id,
        "type": event_type,
        "created": created,
        "data": {"object": obj},
    }


def test_checkout_completed_changes_free_to_pro(db_session):
    tenant, subscription = create_webhook_tenant(db_session)

    event = make_event(
        "evt_checkout_test_001",
        "checkout.session.completed",
        {
            "id": "cs_test_001",
            "object": "checkout.session",
            "mode": "subscription",
            "subscription": "sub_test_001",
            "customer": "cus_webhook_test",
            "client_reference_id": str(tenant.id),
            "metadata": {"tenant_id": str(tenant.id)},
        },
    )

    result = process_stripe_event(db_session, event=event)

    db_session.refresh(subscription)

    assert result["duplicate"] is False
    assert subscription.plan_id == "pro"
    assert subscription.status == "active"
    assert subscription.stripe_subscription_id == "sub_test_001"


def test_duplicate_stripe_event_is_ignored(db_session):
    tenant, subscription = create_webhook_tenant(db_session)

    event = make_event(
        "evt_duplicate_test_001",
        "checkout.session.completed",
        {
            "id": "cs_test_002",
            "object": "checkout.session",
            "mode": "subscription",
            "subscription": "sub_test_002",
            "customer": "cus_webhook_test",
            "client_reference_id": str(tenant.id),
            "metadata": {"tenant_id": str(tenant.id)},
        },
    )

    first = process_stripe_event(db_session, event=event)
    second = process_stripe_event(db_session, event=event)

    assert first["duplicate"] is False
    assert second["duplicate"] is True

    count = db_session.scalar(
        select(func.count())
        .select_from(StripeEvent)
        .where(
            StripeEvent.stripe_event_id == "evt_duplicate_test_001"
        )
    )

    assert count == 1


def test_subscription_deleted_downgrades_to_free(db_session):
    tenant, subscription = create_webhook_tenant(db_session)

    subscription.stripe_subscription_id = "sub_delete_test"
    db_session.flush()

    event = make_event(
        "evt_deleted_test_001",
        "customer.subscription.deleted",
        {
            "id": "sub_delete_test",
            "object": "subscription",
            "customer": "cus_webhook_test",
            "status": "canceled",
            "metadata": {"tenant_id": str(tenant.id)},
            "current_period_start": 1790000000,
            "current_period_end": 1792592000,
        },
    )

    result = process_stripe_event(db_session, event=event)

    db_session.refresh(subscription)

    assert result["duplicate"] is False
    assert subscription.plan_id == "free"
    assert subscription.status == "canceled"


def test_subscription_updated_syncs_plan_and_status(db_session):
    tenant, subscription = create_webhook_tenant(db_session)

    subscription.stripe_subscription_id = "sub_update_test"
    db_session.flush()

    event = make_event(
        "evt_updated_test_001",
        "customer.subscription.updated",
        {
            "id": "sub_update_test",
            "object": "subscription",
            "customer": "cus_webhook_test",
            "status": "past_due",
            "metadata": {"tenant_id": str(tenant.id)},
            "current_period_start": 1790000000,
            "current_period_end": 1792592000,
        },
    )

    result = process_stripe_event(db_session, event=event)

    db_session.refresh(subscription)

    assert result["duplicate"] is False
    assert subscription.plan_id == "free"
    assert subscription.status == "past_due"


def test_older_stripe_event_does_not_regress_subscription(db_session):
    tenant, subscription = create_webhook_tenant(db_session)

    subscription.stripe_subscription_id = "sub_order_test"
    db_session.flush()

    newer_event = make_event(
        "evt_order_newer_001",
        "customer.subscription.updated",
        {
            "id": "sub_order_test",
            "object": "subscription",
            "customer": "cus_webhook_test",
            "status": "active",
            "metadata": {"tenant_id": str(tenant.id)},
            "current_period_start": 1790000100,
            "current_period_end": 1792592100,
        },
        created=1790000100,
    )

    older_event = make_event(
        "evt_order_older_001",
        "customer.subscription.updated",
        {
            "id": "sub_order_test",
            "object": "subscription",
            "customer": "cus_webhook_test",
            "status": "canceled",
            "metadata": {"tenant_id": str(tenant.id)},
            "current_period_start": 1790000000,
            "current_period_end": 1792592000,
        },
        created=1790000000,
    )

    first = process_stripe_event(
        db_session,
        event=newer_event,
    )

    second = process_stripe_event(
        db_session,
        event=older_event,
    )

    db_session.refresh(subscription)

    assert first["duplicate"] is False
    assert second["duplicate"] is False
    assert second["stale"] is True

    assert subscription.plan_id == "pro"
    assert subscription.status == "active"

    assert (
        subscription.last_stripe_event_created_at.timestamp()
        == 1790000100
    )
