
import uuid

from types import SimpleNamespace

import pytest

from app.models.tenant import Tenant
from app.models.plan import Plan
from app.models.subscription import Subscription

from app.services import stripe_customer_service

from app.services.stripe_customer_service import (
    get_or_create_stripe_customer,
)

from app.services.usage_metering_service import (
    TenantNotFoundError,
    SubscriptionNotFoundError,
)


class FakeCustomerService:
    """
    Fake Stripe Customer API for isolated unit testing.
    """

    def __init__(self):
        self.create_calls = []

    def create(
        self,
        *,
        params,
        options,
    ):
        self.create_calls.append(
            {
                "params": params,
                "options": options,
            }
        )

        return SimpleNamespace(
            id="cus_test_flyrank_123",
        )


class FakeStripeClient:
    def __init__(self):
        self.customers = FakeCustomerService()

        self.v1 = SimpleNamespace(
            customers=self.customers,
        )


def _create_tenant_subscription(db_session):
    plan = db_session.get(Plan, "free")

    assert plan is not None

    tenant = Tenant(
        name=f"Stripe Test Tenant {uuid.uuid4()}",
    )

    db_session.add(tenant)
    db_session.flush()

    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id="free",
        status="active",
    )

    db_session.add(subscription)
    db_session.flush()

    return tenant, subscription


def test_creates_stripe_customer_for_new_tenant(
    db_session,
    monkeypatch,
):
    tenant, subscription = _create_tenant_subscription(
        db_session
    )

    fake_client = FakeStripeClient()

    monkeypatch.setattr(
        stripe_customer_service,
        "get_stripe_client",
        lambda: fake_client,
    )

    customer_id = get_or_create_stripe_customer(
        db_session,
        tenant_id=tenant.id,
    )

    assert customer_id == "cus_test_flyrank_123"

    assert subscription.stripe_customer_id == customer_id

    assert len(fake_client.customers.create_calls) == 1

    call = fake_client.customers.create_calls[0]

    assert call["params"]["name"] == tenant.name

    assert call["params"]["metadata"]["tenant_id"] == (
        str(tenant.id)
    )

    assert call["options"]["idempotency_key"] == (
        f"flyrank-customer-{tenant.id}"
    )


def test_reuses_existing_stripe_customer(
    db_session,
    monkeypatch,
):
    tenant, subscription = _create_tenant_subscription(
        db_session
    )

    subscription.stripe_customer_id = "cus_existing_123"

    db_session.flush()

    fake_client = FakeStripeClient()

    monkeypatch.setattr(
        stripe_customer_service,
        "get_stripe_client",
        lambda: fake_client,
    )

    customer_id = get_or_create_stripe_customer(
        db_session,
        tenant_id=tenant.id,
    )

    assert customer_id == "cus_existing_123"

    assert len(fake_client.customers.create_calls) == 0


def test_unknown_tenant_is_rejected(db_session):
    with pytest.raises(TenantNotFoundError):
        get_or_create_stripe_customer(
            db_session,
            tenant_id=uuid.uuid4(),
        )


def test_tenant_without_subscription_is_rejected(
    db_session,
):
    tenant = Tenant(
        name="Tenant Without Subscription",
    )

    db_session.add(tenant)
    db_session.flush()

    with pytest.raises(SubscriptionNotFoundError):
        get_or_create_stripe_customer(
            db_session,
            tenant_id=tenant.id,
        )


def test_customer_creation_failure_rolls_back_database_changes(
    db_session,
    monkeypatch,
):
    tenant, subscription = _create_tenant_subscription(
        db_session
    )

    class FailingCustomerService:
        def create(self, *, params, options):
            raise RuntimeError(
                "Simulated Stripe API failure."
            )

    fake_client = SimpleNamespace(
        v1=SimpleNamespace(
            customers=FailingCustomerService(),
        )
    )

    monkeypatch.setattr(
        stripe_customer_service,
        "get_stripe_client",
        lambda: fake_client,
    )

    with pytest.raises(RuntimeError):
        get_or_create_stripe_customer(
            db_session,
            tenant_id=tenant.id,
        )

    db_session.expire_all()

    refreshed_subscription = db_session.get(
        Subscription,
        subscription.id,
    )

    assert refreshed_subscription.stripe_customer_id is None
