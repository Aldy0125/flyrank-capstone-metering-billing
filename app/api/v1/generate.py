import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.usage import GenerateRequest

from app.services.usage_metering_service import (
    meter_usage_request,
    IdempotencyConflictError,
    TenantNotFoundError,
    PlanNotFoundError,
)


router = APIRouter(
    prefix="/v1",
    tags=["Usage"],
)


@router.post(
    "/generate",
    name="generate_usage",
    responses={
        200: {"description": "Usage recorded successfully."},
        402: {"description": "Subscription or Free quota restriction."},
        404: {"description": "Tenant not found."},
        409: {"description": "Idempotency key conflict."},
        422: {"description": "Invalid request or required headers."},
        429: {"description": "Pro quota exceeded."},
        500: {"description": "Internal subscription configuration error."},
    },
)
def generate(
    request: GenerateRequest,
    tenant_id: Annotated[
        uuid.UUID,
        Header(alias="X-Tenant-ID"),
    ],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
        ),
    ],
    db: Session = Depends(get_db),
):
    """
    Process one billable API operation.

    The metering service handles transaction management,
    idempotency, quota enforcement, and usage recording.
    """

    try:
        result = meter_usage_request(
            db,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            request=request,
        )

    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except TenantNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except PlanNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="Subscription plan configuration is invalid.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    response_headers = {}

    if result.status_code == 429:
        retry_after = result.body.get(
            "retry_after_seconds"
        )

        if retry_after is not None:
            response_headers["Retry-After"] = str(
                retry_after
            )

    return JSONResponse(
        status_code=result.status_code,
        content=result.body,
        headers=response_headers,
    )
