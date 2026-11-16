import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.usage import UsageResponse

from app.services.usage_summary_service import (
    get_usage_summary,
)

from app.services.usage_metering_service import (
    TenantNotFoundError,
    SubscriptionNotFoundError,
    PlanNotFoundError,
)


router = APIRouter(
    prefix="/v1",
    tags=["Usage"],
)


@router.get(
    "/usage",
    name="get_monthly_usage",
    response_model=UsageResponse,
)
def get_usage(
    tenant_id: Annotated[
        uuid.UUID,
        Header(alias="X-Tenant-ID"),
    ],
    db: Session = Depends(get_db),
):
    """
    Retrieve the current monthly usage summary for a tenant.
    """

    try:
        return get_usage_summary(
            db,
            tenant_id=tenant_id,
        )

    except TenantNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except PlanNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="Subscription plan configuration is invalid.",
        ) from exc
