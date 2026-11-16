import uuid

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_db
from app.api.v1 import generate as generate_api

from app.services.usage_metering_service import (
    MeteringResult,
    IdempotencyConflictError,
    TenantNotFoundError,
    PlanNotFoundError,
)


@pytest.fixture
def client():
    """
    Provide a TestClient without opening a database session.

    The metering service is mocked in API contract tests.
    """

    def override_get_db():
        yield None

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


def _valid_headers():
    return {
        "X-Tenant-ID": str(uuid.uuid4()),
        "Idempotency-Key": "api-test-key",
    }


def _valid_payload():
    return {
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 50,
        "reasoning_tokens": 10,
    }


def test_generate_success_returns_http_200(
    client,
    monkeypatch,
):
    def fake_meter(*args, **kwargs):
        assert kwargs["idempotency_key"] == "api-test-key"
        assert kwargs["request"].input_tokens == 100

        return MeteringResult(
            status_code=200,
            body={
                "success": True,
                "usage": {
                    "api_calls": 1,
                    "ai_tokens_used": 150,
                    "cost_micro_usd": 1_580,
                },
            },
        )

    monkeypatch.setattr(
        generate_api,
        "meter_usage_request",
        fake_meter,
    )

    response = client.post(
        "/v1/generate",
        headers=_valid_headers(),
        json=_valid_payload(),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["usage"]["cost_micro_usd"] == 1_580


def test_generate_returns_http_402(
    client,
    monkeypatch,
):
    def fake_meter(*args, **kwargs):
        return MeteringResult(
            status_code=402,
            body={
                "detail": "Free quota exceeded.",
                "code": "quota_exceeded",
            },
        )

    monkeypatch.setattr(
        generate_api,
        "meter_usage_request",
        fake_meter,
    )

    response = client.post(
        "/v1/generate",
        headers=_valid_headers(),
        json=_valid_payload(),
    )

    assert response.status_code == 402
    assert response.json()["code"] == "quota_exceeded"


def test_generate_returns_http_429_with_retry_after(
    client,
    monkeypatch,
):
    def fake_meter(*args, **kwargs):
        return MeteringResult(
            status_code=429,
            body={
                "detail": "Pro quota exceeded.",
                "code": "quota_exceeded",
                "retry_after_seconds": 3_600,
            },
        )

    monkeypatch.setattr(
        generate_api,
        "meter_usage_request",
        fake_meter,
    )

    response = client.post(
        "/v1/generate",
        headers=_valid_headers(),
        json=_valid_payload(),
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"


def test_generate_returns_http_409_for_idempotency_conflict(
    client,
    monkeypatch,
):
    def fake_meter(*args, **kwargs):
        raise IdempotencyConflictError(
            "Idempotency-Key was already used with a different request payload."
        )

    monkeypatch.setattr(
        generate_api,
        "meter_usage_request",
        fake_meter,
    )

    response = client.post(
        "/v1/generate",
        headers=_valid_headers(),
        json=_valid_payload(),
    )

    assert response.status_code == 409
    assert "different request payload" in response.json()["detail"]


def test_generate_returns_http_404_for_unknown_tenant(
    client,
    monkeypatch,
):
    def fake_meter(*args, **kwargs):
        raise TenantNotFoundError(
            "Tenant does not exist."
        )

    monkeypatch.setattr(
        generate_api,
        "meter_usage_request",
        fake_meter,
    )

    response = client.post(
        "/v1/generate",
        headers=_valid_headers(),
        json=_valid_payload(),
    )

    assert response.status_code == 404


def test_generate_rejects_missing_headers(client):
    response = client.post(
        "/v1/generate",
        json=_valid_payload(),
    )

    assert response.status_code == 422


def test_generate_rejects_invalid_tenant_uuid(client):
    headers = _valid_headers()
    headers["X-Tenant-ID"] = "invalid-uuid"

    response = client.post(
        "/v1/generate",
        headers=headers,
        json=_valid_payload(),
    )

    assert response.status_code == 422


def test_generate_rejects_invalid_token_subset(client):
    payload = _valid_payload()
    payload["cached_input_tokens"] = 200

    response = client.post(
        "/v1/generate",
        headers=_valid_headers(),
        json=payload,
    )

    assert response.status_code == 422


def test_generate_rejects_unknown_request_fields(client):
    payload = _valid_payload()
    payload["unexpected_field"] = "not-allowed"

    response = client.post(
        "/v1/generate",
        headers=_valid_headers(),
        json=payload,
    )

    assert response.status_code == 422


def test_generate_returns_http_500_for_missing_plan(
    client,
    monkeypatch,
):
    def fake_meter(*args, **kwargs):
        raise PlanNotFoundError(
            "Plan does not exist."
        )

    monkeypatch.setattr(
        generate_api,
        "meter_usage_request",
        fake_meter,
    )

    response = client.post(
        "/v1/generate",
        headers=_valid_headers(),
        json=_valid_payload(),
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Subscription plan configuration is invalid."
    )
