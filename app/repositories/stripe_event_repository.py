
"""
Stripe event repository.

Provides atomic registration of Stripe webhook events
using PostgreSQL conflict handling.
"""

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.stripe_event import StripeEvent


def register_event_if_new(
    db: Session,
    *,
    stripe_event_id: str,
    event_type: str,
    created_at: datetime,
) -> bool:
    """
    Atomically register a Stripe event if it has not
    already been processed.

    Returns:
        True:
            A new event was inserted.

        False:
            The event already exists and was ignored.

    Important:
        The caller owns transaction commit or rollback.

        This function does not commit the transaction.
        Event registration and business processing must
        be committed together.
    """

    if not stripe_event_id or not stripe_event_id.strip():
        raise ValueError(
            "stripe_event_id cannot be empty."
        )

    if not event_type or not event_type.strip():
        raise ValueError(
            "event_type cannot be empty."
        )

    if (
        created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError(
            "created_at must be timezone-aware."
        )

    # Normalize event timestamp to UTC.
    created_at = created_at.astimezone(timezone.utc)

    statement = (
        insert(StripeEvent)
        .values(
            stripe_event_id=stripe_event_id,
            event_type=event_type,
            created_at=created_at,
        )
        .on_conflict_do_nothing(
            constraint="uq_stripe_events_stripe_event_id",
        )
        .returning(StripeEvent.id)
    )

    inserted_id = db.execute(
        statement
    ).scalar_one_or_none()

    return inserted_id is not None
