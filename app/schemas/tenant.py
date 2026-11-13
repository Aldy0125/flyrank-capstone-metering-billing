import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.schemas.subscription import SubscriptionRead


class TenantCreate(BaseModel):
    """
    Request schema for creating a new tenant.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(
        min_length=1,
        max_length=150,
        description="Name of the tenant organization.",
        examples=["Acme Corporation"],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "Tenant name must not be empty."
            )

        return value


class TenantRead(BaseModel):
    """
    Response schema for tenant information.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    name: str
    created_at: datetime


class TenantWithSubscriptionRead(TenantRead):
    """
    Combined response schema containing tenant
    information and its subscription.
    """

    subscription: SubscriptionRead
