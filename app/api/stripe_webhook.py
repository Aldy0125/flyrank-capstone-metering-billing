from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.stripe_webhook_service import (
    verify_stripe_webhook,
    StripeWebhookConfigurationError,
    InvalidStripeWebhookSignatureError,
    InvalidStripeWebhookPayloadError,
)
from app.services.stripe_subscription_sync_service import (
    process_stripe_event,
    StripeSubscriptionSyncError,
)


router = APIRouter(tags=["Stripe Webhooks"])


@router.post("/webhooks/stripe", name="stripe_webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(
        default=None,
        alias="Stripe-Signature",
    ),
    db: Session = Depends(get_db),
):
    payload = await request.body()

    try:
        event = verify_stripe_webhook(
            payload=payload,
            signature_header=stripe_signature,
        )
    except (
        InvalidStripeWebhookSignatureError,
        InvalidStripeWebhookPayloadError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except StripeWebhookConfigurationError as exc:
        raise HTTPException(
            status_code=500,
            detail="Stripe webhook configuration is invalid.",
        ) from exc

    try:
        return process_stripe_event(
            db,
            event=event,
        )
    except StripeSubscriptionSyncError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
