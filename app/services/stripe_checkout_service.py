
"""
Stripe Checkout service.

Creates subscription Checkout Sessions
for upgrading Free tenants to Pro.
"""

import uuid

from contextlib import nullcontext
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config.settings import settings

from app.integrations.stripe_client import (
    get_stripe_client,
    StripeConfigurationError,
)

from app.repositories.tenant_repository import (
    get_by_id_for_update as get_tenant_by_id_for_update,
)

from app.repositories.subscription_repository import (
    get_by_tenant_id_for_update,
)

from app.repositories.plan_repository import (
    get_by_id as get_plan_by_id,
)

from app.services.stripe_customer_service import (
    get_or_create_stripe_customer,
)

from app.services.usage_metering_service import (
    TenantNotFoundError,
    SubscriptionNotFoundError,
    SubscriptionNotActiveError,
    PlanNotFoundError,
    PlanInactiveError,
)


# ==========================================
# DOMAIN EXCEPTIONS
# ==========================================

class StripeCheckoutError(Exception):
    """Base exception for Checkout operations."""


class AlreadyProSubscriptionError(StripeCheckoutError):
    """Raised when tenant already has a Pro subscription."""


class StripePriceConfigurationError(StripeCheckoutError):
    """Raised when the Pro Price ID is missing or invalid."""


class StripeCheckoutConfigurationError(StripeCheckoutError):
    """Raised when Checkout return URLs are invalid."""


class StripeCheckoutCreationError(StripeCheckoutError):
    """Raised when Stripe Checkout Session creation fails."""


# ==========================================
# CHECKOUT RESULT
# ==========================================

@dataclass(frozen=True)
class CheckoutSessionResult:
    """
    Checkout Session creation result.
    """

    session_id: str
    checkout_url: str
    customer_id: str


# ==========================================
# CONFIGURATION VALIDATION
# ==========================================

def _validate_checkout_configuration() -> None:
    """
    Validate Price ID and Checkout return URLs.
    """

    price_id = settings.stripe_pro_price_id

    if (
        not price_id
        or not price_id.startswith("price_")
        or "replace_with" in price_id.lower()
    ):
        raise StripePriceConfigurationError(
            "A valid STRIPE_PRO_PRICE_ID is required."
        )

    success_url = settings.stripe_checkout_success_url
    cancel_url = settings.stripe_checkout_cancel_url

    for name, value in (
        ("success_url", success_url),
        ("cancel_url", cancel_url),
    ):
        parsed = urlparse(value)

        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
        ):
            raise StripeCheckoutConfigurationError(
                f"Invalid Stripe Checkout {name}."
            )

    if "{CHECKOUT_SESSION_ID}" not in success_url:
        raise StripeCheckoutConfigurationError(
            "success_url must contain "
            "{CHECKOUT_SESSION_ID}."
        )


# ==========================================
# SUBSCRIPTION ELIGIBILITY
# ==========================================

def _validate_upgrade_eligibility(
    db: Session,
    *,
    tenant_id: uuid.UUID,
) -> None:
    """
    Validate that the tenant is eligible for Free-to-Pro upgrade.

    The tenant and subscription rows are locked during validation.
    """

    tenant = get_tenant_by_id_for_update(
        db,
        tenant_id,
    )

    if tenant is None:
        raise TenantNotFoundError(
            f"Tenant '{tenant_id}' does not exist."
        )

    subscription = get_by_tenant_id_for_update(
        db,
        tenant_id,
    )

    if subscription is None:
        raise SubscriptionNotFoundError(
            f"Tenant '{tenant_id}' has no subscription."
        )

    if subscription.status != "active":
        raise SubscriptionNotActiveError(
            f"Subscription status '{subscription.status}' "
            "does not permit Checkout."
        )

    plan = get_plan_by_id(
        db,
        subscription.plan_id,
    )

    if plan is None:
        raise PlanNotFoundError(
            f"Plan '{subscription.plan_id}' does not exist."
        )

    if not plan.is_active:
        raise PlanInactiveError(
            f"Plan '{plan.id}' is inactive."
        )

    if plan.id != "free":
        raise AlreadyProSubscriptionError(
            "Only Free tenants can upgrade to Pro."
        )


# ==========================================
# CREATE CHECKOUT SESSION
# ==========================================

def create_pro_checkout_session(
    db: Session,
    *,
    tenant_id: uuid.UUID,
) -> CheckoutSessionResult:
    """
    Create a Stripe subscription Checkout Session.

    Processing sequence:
    1. Validate Checkout configuration.
    2. Validate tenant and Free subscription.
    3. Retrieve or create Stripe Customer.
    4. Create Stripe Checkout Session.
    5. Return Checkout URL.

    The Stripe Customer is persisted independently
    before Checkout Session creation.

    No subscription upgrade is performed here.
    Verified Stripe webhooks remain responsible
    for synchronizing the Pro subscription.
    """

    _validate_checkout_configuration()

    # Validate tenant and subscription.
    validation_scope = (
        db.begin()
        if not db.in_transaction()
        else nullcontext()
    )

    with validation_scope:
        _validate_upgrade_eligibility(
            db,
            tenant_id=tenant_id,
        )

    # Retrieve or create the Stripe Customer.
    customer_id = get_or_create_stripe_customer(
        db,
        tenant_id=tenant_id,
    )

    # Create Checkout Session.
    try:
        stripe_client = get_stripe_client()

        session = stripe_client.v1.checkout.sessions.create(
            params={
                "mode": "subscription",

                "customer": customer_id,

                "line_items": [
                    {
                        "price": settings.stripe_pro_price_id,
                        "quantity": 1,
                    }
                ],

                "success_url": (
                    settings.stripe_checkout_success_url
                ),

                "cancel_url": (
                    settings.stripe_checkout_cancel_url
                ),

                "client_reference_id": str(tenant_id),

                "metadata": {
                    "tenant_id": str(tenant_id),
                },

                "subscription_data": {
                    "metadata": {
                        "tenant_id": str(tenant_id),
                    },
                },
            },

            options={
                "idempotency_key": (
                    f"flyrank-checkout-{tenant_id}-{uuid.uuid4()}"
                ),
            },
        )

    except StripeConfigurationError:
        raise

    except Exception as exc:
        raise StripeCheckoutCreationError(
            "Unable to create Stripe Checkout Session."
        ) from exc

    if not session.id or not session.url:
        raise StripeCheckoutCreationError(
            "Stripe Checkout Session returned no valid URL."
        )

    return CheckoutSessionResult(
        session_id=session.id,
        checkout_url=session.url,
        customer_id=customer_id,
    )
