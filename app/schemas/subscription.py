import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SubscriptionRead(BaseModel):
    """
    Response schema for subscription information.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    tenant_id: uuid.UUID
    plan_id: str
    status: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    created_at: datetime
    updated_at: datetime
