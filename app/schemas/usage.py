
from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class GenerateRequest(BaseModel):
    """
    Request schema for a simulated billable operation.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    input_tokens: int = Field(
        ge=0,
        strict=True,
        description="Total input tokens.",
    )

    cached_input_tokens: int = Field(
        ge=0,
        strict=True,
        description="Cached input tokens, as a subset of input tokens.",
    )

    output_tokens: int = Field(
        ge=0,
        strict=True,
        description="Total output tokens.",
    )

    reasoning_tokens: int = Field(
        ge=0,
        strict=True,
        description="Reasoning tokens, as a subset of output tokens.",
    )

    @model_validator(mode="after")
    def validate_token_subsets(self):
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError(
                "cached_input_tokens cannot exceed input_tokens."
            )

        if self.reasoning_tokens > self.output_tokens:
            raise ValueError(
                "reasoning_tokens cannot exceed output_tokens."
            )

        return self


class UsageResponse(BaseModel):
    """
    Response schema for monthly tenant usage.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    # Subscription information
    plan_id: str = Field(
        min_length=1,
    )

    subscription_status: str = Field(
        min_length=1,
    )

    # API usage
    api_calls_used: int = Field(
        ge=0,
        strict=True,
    )

    api_calls_remaining: int = Field(
        ge=0,
        strict=True,
    )

    monthly_api_call_limit: int = Field(
        ge=0,
        strict=True,
    )

    # AI token usage
    ai_tokens_used: int = Field(
        ge=0,
        strict=True,
    )

    ai_tokens_remaining: int = Field(
        ge=0,
        strict=True,
    )

    monthly_ai_token_limit: int = Field(
        ge=0,
        strict=True,
    )

    # Accumulated billing cost
    accumulated_cost_micro_usd: int = Field(
        ge=0,
        strict=True,
    )

    # Current UTC billing period
    billing_period_start: date
    billing_period_end: date

    @model_validator(mode="after")
    def validate_usage_limits(self):
        if self.api_calls_used + self.api_calls_remaining != self.monthly_api_call_limit:
            raise ValueError(
                "API calls used and remaining must equal the monthly limit."
            )

        if self.ai_tokens_used + self.ai_tokens_remaining != self.monthly_ai_token_limit:
            raise ValueError(
                "AI tokens used and remaining must equal the monthly limit."
            )

        if self.billing_period_end <= self.billing_period_start:
            raise ValueError(
                "Billing period end must be after billing period start."
            )

        return self
