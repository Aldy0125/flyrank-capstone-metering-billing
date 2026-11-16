
from datetime import datetime, timezone
import uuid

import pytest

from sqlalchemy import func, select

from app.models.stripe_event import StripeEvent

from app.repositories.stripe_event_repository import (
    register_event_if_new,
)


def test_new_stripe_event_is_registered(db_session):
    event_id = f"evt_test_{uuid.uuid4()}"

    created_at = datetime(
        2026, 11, 16, 12, 0,
        tzinfo=timezone.utc,
    )

    result = register_event_if_new(
        db_session,
        stripe_event_id=event_id,
        event_type="checkout.session.completed",
        created_at=created_at,
    )

    assert result is True

    event = db_session.scalar(
        select(StripeEvent).where(
            StripeEvent.stripe_event_id == event_id
        )
    )

    assert event is not None
    assert event.event_type == "checkout.session.completed"
    assert event.created_at is not None


def test_duplicate_stripe_event_is_ignored(db_session):
    event_id = f"evt_test_{uuid.uuid4()}"

    created_at = datetime.now(timezone.utc)

    first_result = register_event_if_new(
        db_session,
        stripe_event_id=event_id,
        event_type="checkout.session.completed",
        created_at=created_at,
    )

    second_result = register_event_if_new(
        db_session,
        stripe_event_id=event_id,
        event_type="checkout.session.completed",
        created_at=created_at,
    )

    assert first_result is True
    assert second_result is False

    count = db_session.scalar(
        select(func.count())
        .select_from(StripeEvent)
        .where(
            StripeEvent.stripe_event_id == event_id
        )
    )

    assert count == 1


def test_different_stripe_events_are_registered(db_session):
    first_id = f"evt_test_{uuid.uuid4()}"
    second_id = f"evt_test_{uuid.uuid4()}"

    created_at = datetime.now(timezone.utc)

    first_result = register_event_if_new(
        db_session,
        stripe_event_id=first_id,
        event_type="checkout.session.completed",
        created_at=created_at,
    )

    second_result = register_event_if_new(
        db_session,
        stripe_event_id=second_id,
        event_type="customer.subscription.updated",
        created_at=created_at,
    )

    assert first_result is True
    assert second_result is True


def test_duplicate_event_does_not_overwrite_original_data(
    db_session,
):
    event_id = f"evt_test_{uuid.uuid4()}"

    original_time = datetime(
        2026, 11, 16, 12, 0,
        tzinfo=timezone.utc,
    )

    register_event_if_new(
        db_session,
        stripe_event_id=event_id,
        event_type="checkout.session.completed",
        created_at=original_time,
    )

    duplicate_result = register_event_if_new(
        db_session,
        stripe_event_id=event_id,
        event_type="customer.subscription.updated",
        created_at=datetime.now(timezone.utc),
    )

    assert duplicate_result is False

    event = db_session.scalar(
        select(StripeEvent).where(
            StripeEvent.stripe_event_id == event_id
        )
    )

    assert event.event_type == "checkout.session.completed"


def test_naive_event_timestamp_is_rejected(db_session):
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        register_event_if_new(
            db_session,
            stripe_event_id=f"evt_test_{uuid.uuid4()}",
            event_type="checkout.session.completed",
            created_at=datetime(2026, 11, 16, 12, 0),
        )


def test_empty_event_id_is_rejected(db_session):
    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        register_event_if_new(
            db_session,
            stripe_event_id="",
            event_type="checkout.session.completed",
            created_at=datetime.now(timezone.utc),
        )


def test_empty_event_type_is_rejected(db_session):
    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        register_event_if_new(
            db_session,
            stripe_event_id=f"evt_test_{uuid.uuid4()}",
            event_type="",
            created_at=datetime.now(timezone.utc),
        )
