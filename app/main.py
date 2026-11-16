
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.generate import router as generate_router
from app.api.v1.usage import router as usage_router
from app.api.v1.billing import router as billing_router

from app.config.settings import settings


app = FastAPI(
    title=settings.app_name,
)


app.include_router(health_router)
app.include_router(generate_router)
app.include_router(usage_router)
app.include_router(billing_router)
