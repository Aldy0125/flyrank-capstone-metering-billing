from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier
import uuid

from sqlalchemy import delete, func, select, text

from app.config.database import SessionLocal

from app.models.tenant import Tenant
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.idempotency import IdempotencyRecord
from app.models.usage_event import UsageEvent

from app.schemas.usage import GenerateRequest

from app.services.usage_metering_service import (
    meter_usage_request,
)


BILLING_PERIOD = date(2026, 11, 1)

TEST_NOW = datetime(
    2026, 11, 16, 12, 0,
    tzinfo=timezone.utc,
)


def _create_committed_tenant(
    *,
    initial_api_calls=0,
):
    """
    Create committed fixtures visible to independent connections.

    Test records are explicitly deleted after each test.
    """

    tenant_id = uuid.uuid4()

    with SessionLocal.begin() as db:
        plan = db.get(Plan, "free")

        assert plan is not None
        assert plan.is_active is True

        tenant = Tenant(
            id=tenant_id,
            name=f"Concurrency Tenant {tenant_id}",
        )

        db.add(tenant)
        db.flush()

        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id="free",
            status="active",
        )

        db.add(subscription)
        db.flush()

        if initial_api_calls:
            prior_record = IdempotencyRecord(
                tenant_id=tenant_id,
                idempotency_key=f"prior-{tenant_id}",
                request_hash="a" * 64,
                response_status=200,
                response_body={"success": True},
            )

            db.add(prior_record)
            db.flush()

            prior_event = UsageEvent(
                tenant_id=tenant_id,
                idempotency_record_id=prior_record.id,
                api_calls=initial_api_calls,
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                cost_micro_usd=0,
                period_start=BILLING_PERIOD,
            )

            db.add(prior_event)

    return tenant_id


def _cleanup_tenant(tenant_id):
    """
    Remove only the temporary tenant created by this test.
    """

    with SessionLocal.begin() as db:
        db.execute(
            delete(UsageEvent).where(
                UsageEvent.tenant_id == tenant_id
            )
        )

        db.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.tenant_id == tenant_id
            )
        )

        db.execute(
            delete(Subscription).where(
                Subscription.tenant_id == tenant_id
            )
        )

        db.execute(
            delete(Tenant).where(
                Tenant.id == tenant_id
            )
        )


def _concurrent_request(
    *,
    tenant_id,
    idempotency_key,
    barrier,
):
    """
    Execute one metering request using an independent session.
    """

    request = GenerateRequest(
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
    )

    with SessionLocal() as db:
        with db.begin():

            # Prevent indefinitely blocked tests.
            db.execute(
                text("SET LOCAL lock_timeout = '5s'")
            )

            # Synchronize both workers before metering.
            barrier.wait(timeout=10)

            result = meter_usage_request(
                db,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                request=request,
                now=TEST_NOW,
            )

            return result


def _get_usage_events(tenant_id):
    with SessionLocal() as db:
        statement = select(UsageEvent).where(
            UsageEvent.tenant_id == tenant_id
        )

        return list(db.scalars(statement).all())


def _count_idempotency_records(tenant_id):
    with SessionLocal() as db:
        statement = (
            select(func.count())
            .select_from(IdempotencyRecord)
            .where(
                IdempotencyRecord.tenant_id == tenant_id
            )
        )

        return db.scalar(statement)


def test_concurrent_requests_cannot_exceed_quota():
    tenant_id = _create_committed_tenant(
        initial_api_calls=999,
    )

    try:
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    _concurrent_request,
                    tenant_id=tenant_id,
                    idempotency_key=f"parallel-{index}",
                    barrier=barrier,
                )
                for index in range(2)
            ]

            results = [
                future.result(timeout=15)
                for future in futures
            ]

        statuses = sorted(
            result.status_code for result in results
        )

        assert statuses == [200, 402]

        events = _get_usage_events(tenant_id)

        assert len(events) == 2

        total_api_calls = sum(
            event.api_calls for event in events
        )

        assert total_api_calls == 1_000

        # One prior record + two new request responses.
        assert _count_idempotency_records(tenant_id) == 3

    finally:
        _cleanup_tenant(tenant_id)


def test_concurrent_same_idempotency_key_creates_one_event():
    tenant_id = _create_committed_tenant()

    try:
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    _concurrent_request,
                    tenant_id=tenant_id,
                    idempotency_key="same-parallel-key",
                    barrier=barrier,
                )
                for _ in range(2)
            ]

            results = [
                future.result(timeout=15)
                for future in futures
            ]

        assert all(
            result.status_code == 200
            for result in results
        )

        replay_count = sum(
            result.replayed for result in results
        )

        assert replay_count == 1

        events = _get_usage_events(tenant_id)

        assert len(events) == 1
        assert events[0].api_calls == 1

        assert _count_idempotency_records(tenant_id) == 1

    finally:
        _cleanup_tenant(tenant_id)
