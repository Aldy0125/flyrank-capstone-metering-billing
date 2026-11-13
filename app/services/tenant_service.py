from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.models.subscription import Subscription

from app.repositories.plan_repository import get_by_id as get_plan_by_id
from app.repositories.tenant_repository import create as create_tenant
from app.repositories.subscription_repository import (
    create as create_subscription,
)


def create_tenant_with_free_subscription(
    db: Session,
    *,
    name: str,
) -> tuple[Tenant, Subscription]:
    """
    Create a tenant and its initial Free subscription
    within a single atomic database transaction.

    Both records are committed together.
    If any operation fails, the entire transaction
    is rolled back.
    """

    with db.begin():

        # 1. Retrieve the default Free plan.
        free_plan = get_plan_by_id(db, "free")

        if free_plan is None:
            raise ValueError(
                "Default Free plan does not exist."
            )

        if not free_plan.is_active:
            raise ValueError(
                "Default Free plan is inactive."
            )

        # 2. Create the tenant.
        tenant = create_tenant(
            db,
            name=name,
        )

        # 3. Create the initial Free subscription.
        subscription = create_subscription(
            db,
            tenant_id=tenant.id,
            plan_id=free_plan.id,
            status="active",
        )

    # Transaction has been committed successfully.
    return tenant, subscription
