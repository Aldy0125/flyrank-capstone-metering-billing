
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.billing import CheckoutSessionResponse

from app.integrations.stripe_client import (
    StripeConfigurationError,
)

from app.services.stripe_checkout_service import (
    create_pro_checkout_session,
    AlreadyProSubscriptionError,
    StripePriceConfigurationError,
    StripeCheckoutConfigurationError,
    StripeCheckoutCreationError,
)

from app.services.usage_metering_service import (
    TenantNotFoundError,
    SubscriptionNotFoundError,
    SubscriptionNotActiveError,
    PlanNotFoundError,
    PlanInactiveError,
)


router = APIRouter(
    prefix="/v1/billing",
    tags=["Billing"],
)


@router.post(
    "/checkout-session",
    name="create_checkout_session",
    response_model=CheckoutSessionResponse,
    responses={
        200: {
            "description": "Checkout Session created successfully."
        },
        402: {
            "description": "Subscription does not permit checkout."
        },
        404: {
            "description": "Tenant or subscription not found."
        },
        409: {
            "description": "Tenant already has a Pro subscription."
        },
        422: {
            "description": "Invalid tenant header."
        },
        500: {
            "description": "Stripe configuration error."
        },
        502: {
            "description": "Stripe Checkout API failure."
        },
    },
)
def create_checkout_session(
    tenant_id: Annotated[
        uuid.UUID,
        Header(alias="X-Tenant-ID"),
    ],
    db: Session = Depends(get_db),
):
    """
    Create a Stripe Checkout Session for upgrading
    a Free tenant to Pro.
    """

    try:
        result = create_pro_checkout_session(
            db,
            tenant_id=tenant_id,
        )

        return CheckoutSessionResponse(
            session_id=result.session_id,
            checkout_url=result.checkout_url,
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

    except SubscriptionNotActiveError as exc:
        raise HTTPException(
            status_code=402,
            detail=str(exc),
        ) from exc

    except AlreadyProSubscriptionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except (
        StripePriceConfigurationError,
        StripeCheckoutConfigurationError,
        StripeConfigurationError,
        PlanNotFoundError,
        PlanInactiveError,
    ) as exc:
        raise HTTPException(
            status_code=500,
            detail="Stripe or subscription configuration is invalid.",
        ) from exc

    except StripeCheckoutCreationError as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to create Stripe Checkout Session.",
        ) from exc
