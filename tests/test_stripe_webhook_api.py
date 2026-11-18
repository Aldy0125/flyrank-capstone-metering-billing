import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_db
from app.api import stripe_webhook as webhook_module

from app.services.stripe_webhook_service import (
    InvalidStripeWebhookSignatureError,
)


@pytest.fixture
def webhook_client():
    def override_db():
        yield object()

    app.dependency_overrides[get_db] = override_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_webhook_valid_signature_returns_200(
    webhook_client,
    monkeypatch,
):
    captured = {}

    def fake_verify(*, payload, signature_header):
        captured["payload"] = payload
        captured["signature"] = signature_header
        return {"id": "evt_http_001", "type": "test.event"}

    def fake_process(db, *, event):
        return {
            "received": True,
            "duplicate": False,
            "event_id": event["id"],
        }

    monkeypatch.setattr(
        webhook_module,
        "verify_stripe_webhook",
        fake_verify,
    )
    monkeypatch.setattr(
        webhook_module,
        "process_stripe_event",
        fake_process,
    )

    response = webhook_client.post(
        "/webhooks/stripe",
        content=b'{"test":true}',
        headers={"Stripe-Signature": "test-signature"},
    )

    assert response.status_code == 200
    assert response.json()["received"] is True
    assert captured["payload"] == b'{"test":true}'
    assert captured["signature"] == "test-signature"


def test_webhook_invalid_signature_returns_400(
    webhook_client,
    monkeypatch,
):
    def fake_verify(**kwargs):
        raise InvalidStripeWebhookSignatureError(
            "Invalid signature."
        )

    monkeypatch.setattr(
        webhook_module,
        "verify_stripe_webhook",
        fake_verify,
    )

    response = webhook_client.post(
        "/webhooks/stripe",
        content=b'{"test":true}',
        headers={"Stripe-Signature": "invalid"},
    )

    assert response.status_code == 400


def test_webhook_missing_signature_returns_400(
    webhook_client,
    monkeypatch,
):
    def fake_verify(**kwargs):
        assert kwargs["signature_header"] is None
        raise InvalidStripeWebhookSignatureError(
            "Stripe-Signature header is missing."
        )

    monkeypatch.setattr(
        webhook_module,
        "verify_stripe_webhook",
        fake_verify,
    )

    response = webhook_client.post(
        "/webhooks/stripe",
        content=b'{"test":true}',
    )

    assert response.status_code == 400


def test_webhook_duplicate_event_returns_200(
    webhook_client,
    monkeypatch,
):
    monkeypatch.setattr(
        webhook_module,
        "verify_stripe_webhook",
        lambda **kwargs: {
            "id": "evt_duplicate_http",
            "type": "checkout.session.completed",
        },
    )

    monkeypatch.setattr(
        webhook_module,
        "process_stripe_event",
        lambda db, event: {
            "received": True,
            "duplicate": True,
            "event_id": event["id"],
        },
    )

    response = webhook_client.post(
        "/webhooks/stripe",
        content=b'{"test":true}',
        headers={"Stripe-Signature": "valid"},
    )

    assert response.status_code == 200
    assert response.json()["duplicate"] is True
