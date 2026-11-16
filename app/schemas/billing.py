
from pydantic import BaseModel, ConfigDict, Field


class CheckoutSessionResponse(BaseModel):
    """
    Response schema for Stripe Checkout Session creation.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    session_id: str = Field(
        min_length=1,
        description="Stripe Checkout Session ID.",
    )

    checkout_url: str = Field(
        min_length=1,
        description="Stripe-hosted Checkout URL.",
    )
