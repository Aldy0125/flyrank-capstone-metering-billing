
import os

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.generate import router as generate_router
from app.api.v1.usage import router as usage_router
from app.api.v1.usage_reports import router as usage_reports_router
from app.api.v1.billing import router as billing_router
from app.api.stripe_webhook import router as stripe_webhook_router

from app.config.settings import settings
from app.integrations.inngest import inngest_client, inngest_functions
from inngest.fast_api import serve


app = FastAPI(
    title=settings.app_name,
)


app.include_router(health_router)
app.include_router(generate_router)
app.include_router(usage_router)
app.include_router(billing_router)
app.include_router(stripe_webhook_router)
app.include_router(usage_reports_router)

is_inngest_dev = os.getenv("INNGEST_DEV", "").lower() not in (
    "",
    "0",
    "false",
    "no",
)

has_signing_key = bool(
    settings.inngest_signing_key
    and settings.inngest_signing_key.get_secret_value().strip()
)

if is_inngest_dev or has_signing_key:
    serve(app, inngest_client, inngest_functions)
