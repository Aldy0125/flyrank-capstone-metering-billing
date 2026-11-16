
"""
Stripe Customer service.

Creates or retrieves a Stripe Customer
associated with a tenant.
"""

import uuid

from contextlib import nullcontext

from sqlalchemy.orm import Session

from app.integrations.stripe_client import get_stripe_client

from app.repositories.tenant_repository import (
    get_by_id_for_update as get_tenant_by_id_for_update,
)

from app.repositories.subscription_repository import (
    get_by_tenant_id_for_update,
    update_stripe_customer_id,
)

from app.services.usage_metering_service import (
    TenantNotFoundError,
    SubscriptionNotFoundError,
)


def get_or_create_stripe_customer(
    db: Session,
    *,
    tenant_id: uuid.UUID,
) -> str:
    """
    Retrieve an existing Stripe Customer or create a new one.

    The tenant row is locked to prevent concurrent requests
    from creating duplicate Stripe Customers.

    A stable Stripe idempotency key ensures that retries
    reuse the same Customer creation operation.

    The caller owns the transaction if one is already active.
    """

    # Preserve an existing caller-owned transaction.
    transaction_scope = (
        db.begin()
        if not db.in_transaction()
        else nullcontext()
    )

    with transaction_scope:

        # 1. Lock tenant row.
        tenant = get_tenant_by_id_for_update(
            db,
            tenant_id,
        )

        if tenant is None:
            raise TenantNotFoundError(
                f"Tenant '{tenant_id}' does not exist."
            )

        # 2. Lock the tenant subscription.
        subscription = get_by_tenant_id_for_update(
            db,
            tenant_id,
        )

        if subscription is None:
            raise SubscriptionNotFoundError(
                f"Tenant '{tenant_id}' has no subscription."
            )

        # 3. Reuse existing Stripe Customer.
        if subscription.stripe_customer_id:
            return subscription.stripe_customer_id

        # 4. Create Stripe Customer.
        stripe_client = get_stripe_client()

        customer = stripe_client.v1.customers.create(
            params={
                "name": tenant.name,
                "metadata": {
                    "tenant_id": str(tenant.id),
                },
            },
            options={
                "idempotency_key": (
                    f"flyrank-customer-{tenant.id}"
                ),
            },
        )

        if not customer.id:
            raise RuntimeError(
                "Stripe Customer creation returned no Customer ID."
            )

        # 5. Persist Stripe Customer reference.
        update_stripe_customer_id(
            db,
            subscription=subscription,
            stripe_customer_id=customer.id,
        )

        return customer.id
