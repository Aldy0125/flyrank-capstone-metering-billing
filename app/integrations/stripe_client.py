
"""
Stripe client factory.

Provides a centralized Stripe SDK client
configured exclusively for Test Mode.
"""

from stripe import StripeClient

from app.config.settings import settings


class StripeConfigurationError(Exception):
    """Raised when Stripe configuration is invalid."""


def get_stripe_client() -> StripeClient:
    """
    Create a StripeClient using the configured Test Secret Key.
    """

    if settings.stripe_secret_key is None:
        raise StripeConfigurationError(
            "STRIPE_SECRET_KEY is not configured."
        )

    secret_key = (
        settings.stripe_secret_key.get_secret_value()
    )

    if not secret_key.startswith("sk_test_"):
        raise StripeConfigurationError(
            "Only Stripe Test Mode keys are permitted."
        )

    return StripeClient(
        secret_key,
        max_network_retries=2,
    )
