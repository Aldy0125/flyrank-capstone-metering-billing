
import json
import time

import pytest

from pydantic import SecretStr
from stripe import WebhookSignature

from app.services import stripe_webhook_service

from app.services.stripe_webhook_service import (
    verify_stripe_webhook,
    StripeWebhookConfigurationError,
    InvalidStripeWebhookSignatureError,
    InvalidStripeWebhookPayloadError,
)


TEST_WEBHOOK_SECRET = "whsec_test_flyrank_secret"


def _valid_payload():
    """
    Create a representative Stripe snapshot event payload.
    """

    event = {
        "id": "evt_test_flyrank_001",
        "object": "event",
        "api_version": "2024-06-20",
        "created": 1730000000,
        "data": {
            "object": {
                "id": "cs_test_flyrank_123",
                "object": "checkout.session",
            }
        },
        "livemode": False,
        "pending_webhooks": 1,
        "type": "checkout.session.completed",
    }

    return json.dumps(
        event,
        separators=(",", ":"),
    ).encode("utf-8")


def _sign_payload(
    payload: bytes,
    *,
    secret=TEST_WEBHOOK_SECRET,
    timestamp=None,
):
    """
    Generate a Stripe-compatible signature for testing.
    """

    return WebhookSignature.generate_signature_header(
        payload.decode("utf-8"),
        secret,
        timestamp,
    )


@pytest.fixture
def webhook_secret(monkeypatch):
    """
    Configure an isolated dummy signing secret.
    """

    monkeypatch.setattr(
        stripe_webhook_service.settings,
        "stripe_webhook_secret",
        SecretStr(TEST_WEBHOOK_SECRET),
    )


def test_valid_webhook_signature_is_accepted(
    webhook_secret,
):
    payload = _valid_payload()

    signature = _sign_payload(payload)

    event = verify_stripe_webhook(
        payload=payload,
        signature_header=signature,
    )

    assert event.id == "evt_test_flyrank_001"

    assert event.type == "checkout.session.completed"

    assert event.livemode is False


def test_invalid_signature_is_rejected(
    webhook_secret,
):
    payload = _valid_payload()

    signature = _sign_payload(
        payload,
        secret="whsec_wrong_secret",
    )

    with pytest.raises(
        InvalidStripeWebhookSignatureError
    ):
        verify_stripe_webhook(
            payload=payload,
            signature_header=signature,
        )


def test_missing_signature_header_is_rejected(
    webhook_secret,
):
    with pytest.raises(
        InvalidStripeWebhookSignatureError
    ):
        verify_stripe_webhook(
            payload=_valid_payload(),
            signature_header=None,
        )


def test_empty_payload_is_rejected(webhook_secret):
    with pytest.raises(
        InvalidStripeWebhookPayloadError
    ):
        verify_stripe_webhook(
            payload=b"",
            signature_header="t=123,v1=invalid",
        )


def test_invalid_json_payload_is_rejected(
    webhook_secret,
):
    payload = b"this-is-not-valid-json"

    signature = _sign_payload(payload)

    with pytest.raises(
        InvalidStripeWebhookPayloadError
    ):
        verify_stripe_webhook(
            payload=payload,
            signature_header=signature,
        )


def test_missing_webhook_secret_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        stripe_webhook_service.settings,
        "stripe_webhook_secret",
        None,
    )

    with pytest.raises(
        StripeWebhookConfigurationError
    ):
        verify_stripe_webhook(
            payload=_valid_payload(),
            signature_header="t=123,v1=invalid",
        )


def test_placeholder_webhook_secret_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        stripe_webhook_service.settings,
        "stripe_webhook_secret",
        SecretStr(
            "whsec_replace_with_webhook_signing_secret"
        ),
    )

    with pytest.raises(
        StripeWebhookConfigurationError
    ):
        verify_stripe_webhook(
            payload=_valid_payload(),
            signature_header="t=123,v1=invalid",
        )


def test_expired_signature_timestamp_is_rejected(
    webhook_secret,
):
    payload = _valid_payload()

    expired_timestamp = int(time.time()) - 600

    signature = _sign_payload(
        payload,
        timestamp=expired_timestamp,
    )

    with pytest.raises(
        InvalidStripeWebhookSignatureError
    ):
        verify_stripe_webhook(
            payload=payload,
            signature_header=signature,
        )


def test_modified_payload_is_rejected(
    webhook_secret,
):
    original_payload = _valid_payload()

    signature = _sign_payload(original_payload)

    modified_payload = original_payload + b" "

    with pytest.raises(
        InvalidStripeWebhookSignatureError
    ):
        verify_stripe_webhook(
            payload=modified_payload,
            signature_header=signature,
        )
