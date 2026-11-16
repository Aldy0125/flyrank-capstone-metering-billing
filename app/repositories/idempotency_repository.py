import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyRecord


def get_by_tenant_and_key(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    idempotency_key: str,
) -> IdempotencyRecord | None:
    """
    Retrieve an idempotency record belonging to a tenant.

    Both tenant_id and idempotency_key are required
    to enforce tenant-scoped idempotency.
    """

    statement = select(IdempotencyRecord).where(
        IdempotencyRecord.tenant_id == tenant_id,
        IdempotencyRecord.idempotency_key == idempotency_key,
    )

    return db.scalar(statement)


def create(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
    response_status: int,
    response_body: dict[str, Any],
) -> IdempotencyRecord:
    """
    Create an idempotency record.

    The caller is responsible for committing
    or rolling back the transaction.
    """

    record = IdempotencyRecord(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status=response_status,
        response_body=response_body,
    )

    db.add(record)
    db.flush()
    db.refresh(record)

    return record
