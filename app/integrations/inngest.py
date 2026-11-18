import asyncio
import json

import inngest
from inngest import Context, Event, Inngest, TriggerEvent

from app.config.settings import settings
from app.config.database import SessionLocal
from app.services.usage_report_worker import (
    process_usage_report_job,
    persist_usage_report_failure,
)


def _secret_value(value):
    return value.get_secret_value() if value else None


inngest_client = Inngest(
    app_id=settings.inngest_app_id,
    event_key=_secret_value(settings.inngest_event_key),
    signing_key=_secret_value(settings.inngest_signing_key),
)


async def _run_report_step(job_id: str) -> dict:
    return await asyncio.to_thread(
        process_usage_report_job,
        job_id,
    )


def _persist_failure_sync(job_id: str, message: str) -> None:
    with SessionLocal.begin() as db:
        persist_usage_report_failure(
            db,
            job_id=job_id,
            error_message=message,
        )


async def _on_usage_report_failure(ctx: Context) -> None:
    data = ctx.event.data or {}

    original_event = data.get("event") or {}
    original_data = (
        original_event.get("data") or {}
        if isinstance(original_event, dict)
        else {}
    )

    job_id = (
        original_data.get("job_id")
        or data.get("job_id")
        or ctx.run_id
    )

    error = data.get("error", "Unknown Inngest failure")

    if isinstance(error, dict):
        message = (
            error.get("message")
            or json.dumps(error, default=str)
        )
    else:
        message = str(error)

    try:
        await asyncio.to_thread(
            _persist_failure_sync,
            str(job_id),
            message,
        )
    except Exception as exc:
        ctx.logger.error(
            f"Unable to persist Inngest failure: {exc}"
        )


async def _generate_usage_report(ctx: Context) -> dict:
    data = ctx.event.data or {}
    job_id = data.get("job_id")

    if not job_id:
        raise inngest.NonRetriableError(
            "Usage report event is missing job_id."
        )

    return await ctx.step.run(
        "generate-monthly-usage-report",
        _run_report_step,
        str(job_id),
    )


generate_usage_report_function = inngest_client.create_function(
    fn_id="generate-usage-report",
    name="Generate Monthly Usage Report",
    trigger=TriggerEvent(
        event="billing/usage-report.requested"
    ),
    retries=3,
    on_failure=_on_usage_report_failure,
)(_generate_usage_report)


inngest_functions = [
    generate_usage_report_function,
]
