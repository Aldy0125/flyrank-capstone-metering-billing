from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Plan(Base):
    """
    Represents a subscription plan and its usage limits.
    """

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
    )

    api_call_limit: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    ai_token_limit: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    monthly_price_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Plan(id={self.id}, "
            f"api_call_limit={self.api_call_limit}, "
            f"ai_token_limit={self.ai_token_limit})>"
        )
