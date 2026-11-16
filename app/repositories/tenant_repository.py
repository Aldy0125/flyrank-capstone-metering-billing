import uuid

from sqlalchemy import select
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


def get_by_id_for_update(
    db: Session,
    tenant_id: uuid.UUID,
) -> Tenant | None:
    """
    Retrieve and lock a tenant row for transactional processing.

    The lock is held until the current database transaction ends.
    """

    statement = (
        select(Tenant)
        .where(Tenant.id == tenant_id)
        .with_for_update()
    )

    return db.scalar(statement)


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
