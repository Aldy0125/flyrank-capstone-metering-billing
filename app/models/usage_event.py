import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UsageEvent(Base):
    """
    Records API and AI token usage for a tenant.
    """

    __tablename__ = "usage_events"

    __table_args__ = (
        UniqueConstraint(
            "idempotency_record_id",
            name="uq_usage_events_idempotency_record_id",
        ),
        Index(
            "ix_usage_events_tenant_period",
            "tenant_id",
            "period_start",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )

    idempotency_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("idempotency_records.id"),
        nullable=False,
    )

    api_calls: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    input_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    cached_input_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    output_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    reasoning_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    cost_micro_usd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    period_start: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<UsageEvent("
            f"id={self.id}, "
            f"tenant_id={self.tenant_id}, "
            f"api_calls={self.api_calls}, "
            f"cost_micro_usd={self.cost_micro_usd})>"
        )
