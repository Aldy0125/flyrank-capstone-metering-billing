
"""
Stripe webhook verification service.

Responsibilities:
- Validate webhook configuration.
- Verify Stripe-Signature header.
- Preserve the original raw request body.
- Reject invalid signatures and payloads.
"""

from stripe import (
    Event,
    SignatureVerificationError,
    Webhook,
)

from app.config.settings import settings


# ==========================================
# WEBHOOK EXCEPTIONS
# ==========================================

class StripeWebhookError(Exception):
    """Base exception for Stripe webhook errors."""


class StripeWebhookConfigurationError(StripeWebhookError):
    """Webhook signing secret is missing or invalid."""


class InvalidStripeWebhookSignatureError(StripeWebhookError):
    """Webhook signature is missing or invalid."""


class InvalidStripeWebhookPayloadError(StripeWebhookError):
    """Webhook payload is empty or malformed."""


# ==========================================
# SIGNATURE VERIFICATION
# ==========================================

def verify_stripe_webhook(
    *,
    payload: bytes,
    signature_header: str | None,
) -> Event:
    """
    Verify and construct a Stripe webhook event.

    Important:
    - The original raw HTTP request body must be provided.
    - The Stripe-Signature header must be provided.
    - The webhook signing secret must be valid.
    - No event processing occurs in this function.

    Returns:
        Verified Stripe Event object.

    Raises:
        StripeWebhookConfigurationError:
            Missing or placeholder webhook secret.

        InvalidStripeWebhookSignatureError:
            Missing or invalid Stripe signature.

        InvalidStripeWebhookPayloadError:
            Empty, malformed, or invalid JSON payload.
    """

    # 1. Validate raw payload.
    if not isinstance(payload, bytes) or not payload:
        raise InvalidStripeWebhookPayloadError(
            "Webhook payload must be non-empty raw bytes."
        )

    # 2. Validate webhook signing secret.
    configured_secret = settings.stripe_webhook_secret

    if configured_secret is None:
        raise StripeWebhookConfigurationError(
            "STRIPE_WEBHOOK_SECRET is not configured."
        )

    webhook_secret = (
        configured_secret.get_secret_value()
    )

    if (
        not webhook_secret.startswith("whsec_")
        or "replace_with" in webhook_secret.lower()
    ):
        raise StripeWebhookConfigurationError(
            "STRIPE_WEBHOOK_SECRET is invalid or still a placeholder."
        )

    # 3. Validate signature header.
    if (
        not isinstance(signature_header, str)
        or not signature_header.strip()
    ):
        raise InvalidStripeWebhookSignatureError(
            "Stripe-Signature header is missing."
        )

    # 4. Verify signature and construct event.
    try:
        event = Webhook.construct_event(
            payload=payload,
            sig_header=signature_header,
            secret=webhook_secret,
        )

    except SignatureVerificationError as exc:
        raise InvalidStripeWebhookSignatureError(
            "Stripe webhook signature verification failed."
        ) from exc

    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidStripeWebhookPayloadError(
            "Stripe webhook payload is invalid."
        ) from exc

    return event
