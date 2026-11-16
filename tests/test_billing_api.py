
import uuid

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_db

from app.api.v1 import billing as billing_api

from app.integrations.stripe_client import (
    StripeConfigurationError,
)

from app.services.stripe_checkout_service import (
    CheckoutSessionResult,
    AlreadyProSubscriptionError,
    StripePriceConfigurationError,
    StripeCheckoutConfigurationError,
    StripeCheckoutCreationError,
)

from app.services.usage_metering_service import (
    TenantNotFoundError,
    SubscriptionNotFoundError,
    SubscriptionNotActiveError,
    PlanNotFoundError,
    PlanInactiveError,
)


@pytest.fixture
def client():
    """
    Provide an isolated API test client.

    Stripe Checkout Service is mocked.
    No real Stripe API calls are performed.
    """

    def override_get_db():
        yield None

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


def _headers():
    return {
        "X-Tenant-ID": str(uuid.uuid4()),
    }


def test_checkout_session_returns_http_200(
    client,
    monkeypatch,
):
    def fake_checkout(*args, **kwargs):
        return CheckoutSessionResult(
            session_id="cs_test_flyrank_123",
            checkout_url="https://checkout.stripe.com/test",
            customer_id="cus_test_flyrank_123",
        )

    monkeypatch.setattr(
        billing_api,
        "create_pro_checkout_session",
        fake_checkout,
    )

    response = client.post(
        "/v1/billing/checkout-session",
        headers=_headers(),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["session_id"] == "cs_test_flyrank_123"

    assert body["checkout_url"] == (
        "https://checkout.stripe.com/test"
    )

    assert "customer_id" not in body


def test_checkout_returns_404_for_unknown_tenant(
    client,
    monkeypatch,
):
    def fake_checkout(*args, **kwargs):
        raise TenantNotFoundError(
            "Tenant does not exist."
        )

    monkeypatch.setattr(
        billing_api,
        "create_pro_checkout_session",
        fake_checkout,
    )

    response = client.post(
        "/v1/billing/checkout-session",
        headers=_headers(),
    )

    assert response.status_code == 404


def test_checkout_returns_404_without_subscription(
    client,
    monkeypatch,
):
    def fake_checkout(*args, **kwargs):
        raise SubscriptionNotFoundError(
            "Subscription does not exist."
        )

    monkeypatch.setattr(
        billing_api,
        "create_pro_checkout_session",
        fake_checkout,
    )

    response = client.post(
        "/v1/billing/checkout-session",
        headers=_headers(),
    )

    assert response.status_code == 404


def test_checkout_returns_402_for_inactive_subscription(
    client,
    monkeypatch,
):
    def fake_checkout(*args, **kwargs):
        raise SubscriptionNotActiveError(
            "Subscription is inactive."
        )

    monkeypatch.setattr(
        billing_api,
        "create_pro_checkout_session",
        fake_checkout,
    )

    response = client.post(
        "/v1/billing/checkout-session",
        headers=_headers(),
    )

    assert response.status_code == 402


def test_checkout_returns_409_for_existing_pro_subscription(
    client,
    monkeypatch,
):
    def fake_checkout(*args, **kwargs):
        raise AlreadyProSubscriptionError(
            "Tenant already has Pro."
        )

    monkeypatch.setattr(
        billing_api,
        "create_pro_checkout_session",
        fake_checkout,
    )

    response = client.post(
        "/v1/billing/checkout-session",
        headers=_headers(),
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "exception",
    [
        StripePriceConfigurationError(
            "Price ID is missing."
        ),
        StripeCheckoutConfigurationError(
            "Checkout URL is invalid."
        ),
        StripeConfigurationError(
            "Stripe key is missing."
        ),
        PlanNotFoundError(
            "Plan does not exist."
        ),
        PlanInactiveError(
            "Plan is inactive."
        ),
    ],
)
def test_checkout_returns_500_for_configuration_errors(
    client,
    monkeypatch,
    exception,
):
    def fake_checkout(*args, **kwargs):
        raise exception

    monkeypatch.setattr(
        billing_api,
        "create_pro_checkout_session",
        fake_checkout,
    )

    response = client.post(
        "/v1/billing/checkout-session",
        headers=_headers(),
    )

    assert response.status_code == 500


def test_checkout_returns_502_for_stripe_api_failure(
    client,
    monkeypatch,
):
    def fake_checkout(*args, **kwargs):
        raise StripeCheckoutCreationError(
            "Stripe Checkout failed."
        )

    monkeypatch.setattr(
        billing_api,
        "create_pro_checkout_session",
        fake_checkout,
    )

    response = client.post(
        "/v1/billing/checkout-session",
        headers=_headers(),
    )

    assert response.status_code == 502


def test_checkout_rejects_missing_tenant_header(client):
    response = client.post(
        "/v1/billing/checkout-session",
    )

    assert response.status_code == 422


def test_checkout_rejects_invalid_tenant_uuid(client):
    response = client.post(
        "/v1/billing/checkout-session",
        headers={
            "X-Tenant-ID": "invalid-uuid",
        },
    )

    assert response.status_code == 422
