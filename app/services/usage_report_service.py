import uuid
import calendar
from datetime import date

from sqlalchemy.orm import Session

from app.repositories.usage_repository import get_monthly_usage


def generate_usage_report(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    period_start: date,
) -> dict:

    if period_start.day != 1:
        raise ValueError(
            "period_start must be the first day of a month."
        )

    period_end = date(
        period_start.year,
        period_start.month,
        calendar.monthrange(
            period_start.year,
            period_start.month,
        )[1],
    )

    usage = get_monthly_usage(
        db,
        tenant_id=tenant_id,
        period_start=period_start,
    )

    return {
        "report_type": "monthly_usage",
        "tenant_id": str(tenant_id),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "api_calls": usage["api_calls"],
        "input_tokens": usage["input_tokens"],
        "cached_input_tokens": usage["cached_input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": usage["reasoning_tokens"],
        "ai_tokens_used": usage["ai_tokens_used"],
        "cost_micro_usd": usage["cost_micro_usd"],
    }
