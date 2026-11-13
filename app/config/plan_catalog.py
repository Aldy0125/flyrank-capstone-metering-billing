from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlanDefinition:
    """
    Immutable definition of a subscription plan.
    """

    id: str
    api_call_limit: int
    ai_token_limit: int
    monthly_price_cents: int
    currency: str = "USD"
    is_active: bool = True


# Free subscription plan
FREE_PLAN = PlanDefinition(
    id="free",
    api_call_limit=1_000,
    ai_token_limit=100_000,
    monthly_price_cents=0,
)


# Pro subscription plan
PRO_PLAN = PlanDefinition(
    id="pro",
    api_call_limit=10_000,
    ai_token_limit=1_000_000,
    monthly_price_cents=2_900,
)


# Central catalog of available plans
DEFAULT_PLANS = (
    FREE_PLAN,
    PRO_PLAN,
)
