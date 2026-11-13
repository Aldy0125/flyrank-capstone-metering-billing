import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JobFailure(Base):
    """
    Stores permanent background job failures
    for operational monitoring and debugging.
    """

    __tablename__ = "job_failures"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    function_id: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    job_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<JobFailure("
            f"id={self.id}, "
            f"function_id={self.function_id}, "
            f"job_id={self.job_id})>"
        )
