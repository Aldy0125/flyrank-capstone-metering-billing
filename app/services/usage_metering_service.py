"""
Usage metering service.

Responsibilities:
- Integer micro-USD cost calculation.
- UTC calendar billing period.
- Tenant subscription and plan validation.
- Idempotency handling.
- Quota enforcement.
- Atomic usage event recording.
"""

import hashlib
import json
import uuid

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import ceil
from typing import Any

from sqlalchemy.orm import Session

from app.models.subscription import Subscription
from app.models.plan import Plan

from app.schemas.usage import GenerateRequest

from app.repositories.tenant_repository import (
    get_by_id as get_tenant_by_id,
    get_by_id_for_update as get_tenant_by_id_for_update,
)

from app.repositories.subscription_repository import (
    get_by_tenant_id as get_subscription_by_tenant_id,
)

from app.repositories.plan_repository import (
    get_by_id as get_plan_by_id,
)

from app.repositories.idempotency_repository import (
    create as create_idempotency_record,
    get_by_tenant_and_key,
)

from app.repositories.usage_repository import (
    create as create_usage_event,
    get_monthly_usage,
)


# ==========================================
# PRICING CONSTANTS
# ==========================================

API_CALL_COST_MICRO_USD = 1_000
FRESH_INPUT_COST_MICRO_USD = 2
CACHED_INPUT_COST_MICRO_USD = 1
OUTPUT_COST_MICRO_USD = 8


# ==========================================
# DOMAIN EXCEPTIONS
# ==========================================

class MeteringValidationError(Exception):
    """Base exception for metering validation errors."""


class TenantNotFoundError(MeteringValidationError):
    """Tenant does not exist."""


class SubscriptionNotFoundError(MeteringValidationError):
    """Tenant has no subscription."""


class SubscriptionNotActiveError(MeteringValidationError):
    """Subscription does not permit usage."""


class PlanNotFoundError(MeteringValidationError):
    """Subscription plan does not exist."""


class PlanInactiveError(MeteringValidationError):
    """Subscription plan is inactive."""


class IdempotencyConflictError(MeteringValidationError):
    """Idempotency key was reused with a different payload."""


# ==========================================
# METERING RESULT
# ==========================================

@dataclass(frozen=True)
class MeteringResult:
    """
    Result returned by the usage metering operation.

    status_code:
        HTTP response status.

    body:
        Original response body stored for idempotency.

    replayed:
        True when returning an existing idempotency response.
    """

    status_code: int
    body: dict[str, Any]
    replayed: bool = False


# ==========================================
# COST CALCULATION
# ==========================================

def calculate_cost_micro_usd(
    *,
    api_calls: int,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> int:

    quantities = {
        "api_calls": api_calls,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
    }

    for name, value in quantities.items():
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer.")

        if value < 0:
            raise ValueError(f"{name} cannot be negative.")

    if cached_input_tokens > input_tokens:
        raise ValueError(
            "cached_input_tokens cannot exceed input_tokens."
        )

    if reasoning_tokens > output_tokens:
        raise ValueError(
            "reasoning_tokens cannot exceed output_tokens."
        )

    fresh_input_tokens = input_tokens - cached_input_tokens

    return (
        (api_calls * API_CALL_COST_MICRO_USD)
        + (fresh_input_tokens * FRESH_INPUT_COST_MICRO_USD)
        + (cached_input_tokens * CACHED_INPUT_COST_MICRO_USD)
        + (output_tokens * OUTPUT_COST_MICRO_USD)
    )


# ==========================================
# UTC BILLING PERIOD
# ==========================================

def _normalize_utc_datetime(
    now: datetime | None = None,
) -> datetime:

    if now is None:
        return datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(
            "now must be a timezone-aware datetime."
        )

    return now.astimezone(timezone.utc)


def get_utc_billing_period(
    now: datetime | None = None,
) -> tuple[date, date]:

    current_utc = _normalize_utc_datetime(now)

    period_start = date(
        current_utc.year,
        current_utc.month,
        1,
    )

    if current_utc.month == 12:
        next_month_start = date(
            current_utc.year + 1,
            1,
            1,
        )
    else:
        next_month_start = date(
            current_utc.year,
            current_utc.month + 1,
            1,
        )

    period_end = next_month_start - timedelta(days=1)

    return period_start, period_end


def get_seconds_until_next_utc_period(
    now: datetime | None = None,
) -> int:

    current_utc = _normalize_utc_datetime(now)

    if current_utc.month == 12:
        next_month_start = datetime(
            current_utc.year + 1,
            1,
            1,
            tzinfo=timezone.utc,
        )
    else:
        next_month_start = datetime(
            current_utc.year,
            current_utc.month + 1,
            1,
            tzinfo=timezone.utc,
        )

    remaining_seconds = (
        next_month_start - current_utc
    ).total_seconds()

    return max(1, ceil(remaining_seconds))


# ==========================================
# SUBSCRIPTION AND PLAN VALIDATION
# ==========================================

def get_active_subscription_context(
    db: Session,
    *,
    tenant_id: uuid.UUID,
) -> tuple[Subscription, Plan]:

    tenant = get_tenant_by_id(db, tenant_id)

    if tenant is None:
        raise TenantNotFoundError(
            f"Tenant '{tenant_id}' does not exist."
        )

    subscription = get_subscription_by_tenant_id(
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
            "does not permit usage."
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

    return subscription, plan


# ==========================================
# IDEMPOTENCY HELPERS
# ==========================================

def calculate_request_hash(
    request: GenerateRequest,
) -> str:
    """
    Generate a deterministic SHA-256 request hash.
    """

    normalized_payload = request.model_dump(mode="json")

    canonical_payload = json.dumps(
        normalized_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical_payload.encode("utf-8")
    ).hexdigest()


def _validate_idempotency_key(
    idempotency_key: str,
) -> None:

    if not isinstance(idempotency_key, str):
        raise ValueError(
            "Idempotency-Key must be a string."
        )

    if not idempotency_key.strip():
        raise ValueError(
            "Idempotency-Key cannot be empty."
        )

    if len(idempotency_key) > 255:
        raise ValueError(
            "Idempotency-Key cannot exceed 255 characters."
        )


def _store_idempotency_response(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
    status_code: int,
    body: dict[str, Any],
) -> None:
    """
    Persist the original response.

    The caller must execute this inside the metering transaction.
    """

    create_idempotency_record(
        db,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status=status_code,
        response_body=body,
    )


# ==========================================
# ATOMIC USAGE METERING
# ==========================================

def meter_usage_request(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    idempotency_key: str,
    request: GenerateRequest,
    now: datetime | None = None,
) -> MeteringResult:
    """
    Process one billable API operation atomically.

    Transaction sequence:
    1. Lock tenant row.
    2. Check idempotency.
    3. Validate subscription and plan.
    4. Aggregate current usage.
    5. Enforce quota.
    6. Calculate cost.
    7. Insert idempotency record.
    8. Insert usage event.
    9. Commit when this service owns the transaction.

    If a caller already owns an active transaction,
    the caller remains responsible for commit or rollback.
    """

    _validate_idempotency_key(idempotency_key)

    request_hash = calculate_request_hash(request)

    result: MeteringResult

    # Start a transaction when the caller has not started one.
    # Existing caller-owned transactions are preserved.
    transaction_scope = (
        db.begin()
        if not db.in_transaction()
        else nullcontext()
    )

    with transaction_scope:

        # 1. Lock tenant row.
        tenant = get_tenant_by_id_for_update(
            db,
            tenant_id,
        )

        if tenant is None:
            raise TenantNotFoundError(
                f"Tenant '{tenant_id}' does not exist."
            )

        # 2. Check idempotency after acquiring the tenant lock.
        existing_record = get_by_tenant_and_key(
            db,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
        )

        if existing_record is not None:

            if existing_record.request_hash != request_hash:
                raise IdempotencyConflictError(
                    "Idempotency-Key was already used "
                    "with a different request payload."
                )

            result = MeteringResult(
                status_code=existing_record.response_status,
                body=existing_record.response_body,
                replayed=True,
            )

        else:

            # 3. Validate subscription and plan.
            try:
                _, plan = get_active_subscription_context(
                    db,
                    tenant_id=tenant_id,
                )

            except (
                SubscriptionNotFoundError,
                SubscriptionNotActiveError,
                PlanInactiveError,
            ) as exc:

                rejection_body = {
                    "detail": str(exc),
                    "code": "subscription_not_active",
                }

                _store_idempotency_response(
                    db,
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    status_code=402,
                    body=rejection_body,
                )

                result = MeteringResult(
                    status_code=402,
                    body=rejection_body,
                )

            else:

                # 4. Determine current UTC billing period.
                period_start, period_end = (
                    get_utc_billing_period(now)
                )

                # 5. Aggregate accepted usage events.
                current_usage = get_monthly_usage(
                    db,
                    tenant_id=tenant_id,
                    period_start=period_start,
                )

                requested_api_calls = 1

                requested_ai_tokens = (
                    request.input_tokens
                    + request.output_tokens
                )

                next_api_calls = (
                    current_usage["api_calls"]
                    + requested_api_calls
                )

                next_ai_tokens = (
                    current_usage["ai_tokens_used"]
                    + requested_ai_tokens
                )

                api_quota_exceeded = (
                    next_api_calls > plan.api_call_limit
                )

                token_quota_exceeded = (
                    next_ai_tokens > plan.ai_token_limit
                )

                # 6. Reject quota violations without creating
                # a usage event.
                if api_quota_exceeded or token_quota_exceeded:

                    if plan.id == "free":
                        status_code = 402

                    elif plan.id == "pro":
                        status_code = 429

                    else:
                        raise MeteringValidationError(
                            f"Unsupported plan '{plan.id}'."
                        )

                    violations = []

                    if api_quota_exceeded:
                        violations.append(
                            "Monthly API call quota exceeded."
                        )

                    if token_quota_exceeded:
                        violations.append(
                            "Monthly AI token quota exceeded."
                        )

                    rejection_body = {
                        "detail": " ".join(violations),
                        "code": "quota_exceeded",
                        "api_calls_used": current_usage["api_calls"],
                        "api_calls_requested": requested_api_calls,
                        "api_call_limit": plan.api_call_limit,
                        "ai_tokens_used": current_usage["ai_tokens_used"],
                        "ai_tokens_requested": requested_ai_tokens,
                        "ai_token_limit": plan.ai_token_limit,
                    }

                    if status_code == 429:
                        rejection_body["retry_after_seconds"] = (
                            get_seconds_until_next_utc_period(now)
                        )

                    _store_idempotency_response(
                        db,
                        tenant_id=tenant_id,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        status_code=status_code,
                        body=rejection_body,
                    )

                    result = MeteringResult(
                        status_code=status_code,
                        body=rejection_body,
                    )

                else:

                    # 7. Calculate usage cost.
                    cost_micro_usd = calculate_cost_micro_usd(
                        api_calls=1,
                        input_tokens=request.input_tokens,
                        cached_input_tokens=request.cached_input_tokens,
                        output_tokens=request.output_tokens,
                        reasoning_tokens=request.reasoning_tokens,
                    )

                    success_body = {
                        "success": True,
                        "usage": {
                            "api_calls": 1,
                            "input_tokens": request.input_tokens,
                            "cached_input_tokens": request.cached_input_tokens,
                            "output_tokens": request.output_tokens,
                            "reasoning_tokens": request.reasoning_tokens,
                            "ai_tokens_used": requested_ai_tokens,
                            "cost_micro_usd": cost_micro_usd,
                            "billing_period_start": period_start.isoformat(),
                            "billing_period_end": period_end.isoformat(),
                        },
                    }

                    # 8. Create idempotency record first because
                    # usage_events references its primary key.
                    idempotency_record = create_idempotency_record(
                        db,
                        tenant_id=tenant_id,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response_status=200,
                        response_body=success_body,
                    )

                    # 9. Create exactly one accepted usage event.
                    create_usage_event(
                        db,
                        tenant_id=tenant_id,
                        idempotency_record_id=idempotency_record.id,
                        api_calls=1,
                        input_tokens=request.input_tokens,
                        cached_input_tokens=request.cached_input_tokens,
                        output_tokens=request.output_tokens,
                        reasoning_tokens=request.reasoning_tokens,
                        cost_micro_usd=cost_micro_usd,
                        period_start=period_start,
                    )

                    result = MeteringResult(
                        status_code=200,
                        body=success_body,
                    )

    return result
