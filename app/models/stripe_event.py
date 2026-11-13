import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StripeEvent(Base):
    """
    Stores processed Stripe webhook event identifiers
    to prevent duplicate event processing.
    """

    __tablename__ = "stripe_events"

    __table_args__ = (
        UniqueConstraint(
            "stripe_event_id",
            name="uq_stripe_events_stripe_event_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    stripe_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<StripeEvent("
            f"id={self.id}, "
            f"stripe_event_id={self.stripe_event_id}, "
            f"event_type={self.event_type})>"
        )
