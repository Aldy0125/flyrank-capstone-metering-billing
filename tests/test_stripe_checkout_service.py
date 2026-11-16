
import uuid

from types import SimpleNamespace

import pytest

from app.models.tenant import Tenant
from app.models.plan import Plan
from app.models.subscription import Subscription

from app.config.settings import settings

from app.services import stripe_checkout_service

from app.services.stripe_checkout_service import (
    create_pro_checkout_session,
    AlreadyProSubscriptionError,
    StripePriceConfigurationError,
    StripeCheckoutCreationError,
)

from app.services.usage_metering_service import (
    TenantNotFoundError,
    SubscriptionNotFoundError,
    SubscriptionNotActiveError,
)


class FakeCheckoutSessions:
    """
    Fake Stripe Checkout Sessions API.
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
            id="cs_test_flyrank_123",
            url="https://checkout.stripe.com/test-session",
        )


class FakeStripeClient:
    def __init__(self):
        self.checkout_sessions = FakeCheckoutSessions()

        self.v1 = SimpleNamespace(
            checkout=SimpleNamespace(
                sessions=self.checkout_sessions,
            )
        )


def _create_tenant_subscription(
    db_session,
    *,
    plan_id="free",
    status="active",
):
    plan = db_session.get(Plan, plan_id)

    assert plan is not None

    tenant = Tenant(
        name=f"Checkout Tenant {uuid.uuid4()}",
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

    return tenant, subscription


def _mock_customer_creation(monkeypatch):
    monkeypatch.setattr(
        stripe_checkout_service,
        "get_or_create_stripe_customer",
        lambda db, *, tenant_id: "cus_test_flyrank_123",
    )


def _mock_checkout_client(monkeypatch):
    fake_client = FakeStripeClient()

    monkeypatch.setattr(
        stripe_checkout_service,
        "get_stripe_client",
        lambda: fake_client,
    )

    return fake_client


def test_creates_pro_checkout_session(
    db_session,
    monkeypatch,
):
    tenant, _ = _create_tenant_subscription(
        db_session,
    )

    _mock_customer_creation(monkeypatch)

    fake_client = _mock_checkout_client(monkeypatch)

    result = create_pro_checkout_session(
        db_session,
        tenant_id=tenant.id,
    )

    assert result.session_id == "cs_test_flyrank_123"

    assert result.checkout_url == (
        "https://checkout.stripe.com/test-session"
    )

    assert result.customer_id == "cus_test_flyrank_123"

    assert len(fake_client.checkout_sessions.create_calls) == 1

    call = fake_client.checkout_sessions.create_calls[0]

    params = call["params"]

    assert params["mode"] == "subscription"

    assert params["customer"] == "cus_test_flyrank_123"

    assert params["line_items"] == [
        {
            "price": settings.stripe_pro_price_id,
            "quantity": 1,
        }
    ]

    assert params["metadata"]["tenant_id"] == str(tenant.id)

    assert params["subscription_data"]["metadata"]["tenant_id"] == (
        str(tenant.id)
    )

    assert params["client_reference_id"] == str(tenant.id)

    assert "{CHECKOUT_SESSION_ID}" in params["success_url"]

    assert call["options"]["idempotency_key"].startswith(
        f"flyrank-checkout-{tenant.id}-"
    )


def test_existing_pro_subscription_is_rejected(
    db_session,
    monkeypatch,
):
    tenant, _ = _create_tenant_subscription(
        db_session,
        plan_id="pro",
    )

    customer_called = False

    def fake_customer(*args, **kwargs):
        nonlocal customer_called
        customer_called = True
        return "cus_test"

    monkeypatch.setattr(
        stripe_checkout_service,
        "get_or_create_stripe_customer",
        fake_customer,
    )

    with pytest.raises(AlreadyProSubscriptionError):
        create_pro_checkout_session(
            db_session,
            tenant_id=tenant.id,
        )

    assert customer_called is False


def test_inactive_subscription_is_rejected(db_session):
    tenant, _ = _create_tenant_subscription(
        db_session,
        status="past_due",
    )

    with pytest.raises(SubscriptionNotActiveError):
        create_pro_checkout_session(
            db_session,
            tenant_id=tenant.id,
        )


def test_unknown_tenant_is_rejected(db_session):
    with pytest.raises(TenantNotFoundError):
        create_pro_checkout_session(
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
        create_pro_checkout_session(
            db_session,
            tenant_id=tenant.id,
        )


def test_missing_price_id_is_rejected(
    db_session,
    monkeypatch,
):
    tenant, _ = _create_tenant_subscription(
        db_session,
    )

    monkeypatch.setattr(
        stripe_checkout_service.settings,
        "stripe_pro_price_id",
        None,
    )

    with pytest.raises(StripePriceConfigurationError):
        create_pro_checkout_session(
            db_session,
            tenant_id=tenant.id,
        )


def test_stripe_checkout_api_failure_is_handled(
    db_session,
    monkeypatch,
):
    tenant, _ = _create_tenant_subscription(
        db_session,
    )

    _mock_customer_creation(monkeypatch)

    class FailingCheckoutSessions:
        def create(self, *, params, options):
            raise RuntimeError(
                "Simulated Stripe API failure."
            )

    fake_client = SimpleNamespace(
        v1=SimpleNamespace(
            checkout=SimpleNamespace(
                sessions=FailingCheckoutSessions(),
            )
        )
    )

    monkeypatch.setattr(
        stripe_checkout_service,
        "get_stripe_client",
        lambda: fake_client,
    )

    with pytest.raises(StripeCheckoutCreationError):
        create_pro_checkout_session(
            db_session,
            tenant_id=tenant.id,
        )


def test_checkout_session_without_url_is_rejected(
    db_session,
    monkeypatch,
):
    tenant, _ = _create_tenant_subscription(
        db_session,
    )

    _mock_customer_creation(monkeypatch)

    fake_client = SimpleNamespace(
        v1=SimpleNamespace(
            checkout=SimpleNamespace(
                sessions=SimpleNamespace(
                    create=lambda **kwargs: SimpleNamespace(
                        id="cs_test_missing_url",
                        url=None,
                    )
                )
            )
        )
    )

    monkeypatch.setattr(
        stripe_checkout_service,
        "get_stripe_client",
        lambda: fake_client,
    )

    with pytest.raises(StripeCheckoutCreationError):
        create_pro_checkout_session(
            db_session,
            tenant_id=tenant.id,
        )


def test_invalid_success_url_is_rejected(
    db_session,
    monkeypatch,
):
    tenant, _ = _create_tenant_subscription(
        db_session,
    )

    monkeypatch.setattr(
        stripe_checkout_service.settings,
        "stripe_checkout_success_url",
        "http://localhost:8000/docs",
    )

    with pytest.raises(
        stripe_checkout_service.StripeCheckoutConfigurationError
    ):
        create_pro_checkout_session(
            db_session,
            tenant_id=tenant.id,
        )
