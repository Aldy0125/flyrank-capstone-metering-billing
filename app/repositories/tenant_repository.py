import uuid

from sqlalchemy.orm import Session

from app.models.tenant import Tenant


def get_by_id(
    db: Session,
    tenant_id: uuid.UUID,
) -> Tenant | None:
    """
    Retrieve a tenant by its UUID.
    """

    return db.get(Tenant, tenant_id)


def create(
    db: Session,
    *,
    name: str,
) -> Tenant:
    """
    Create a new tenant.

    The caller is responsible for committing
    or rolling back the transaction.
    """

    tenant = Tenant(
        name=name,
    )

    db.add(tenant)
    db.flush()
    db.refresh(tenant)

    return tenant
