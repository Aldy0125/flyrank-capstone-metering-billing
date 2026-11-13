from fastapi import FastAPI

from app.api.health import router as health_router
from app.config.settings import settings


# Initialize FastAPI application
app = FastAPI(
    title=settings.app_name,
)


# Register API routers
app.include_router(health_router)
