from sqlalchemy.orm import Session

from app.models.plan import Plan


def get_by_id(
    db: Session,
    plan_id: str,
) -> Plan | None:
    """
    Retrieve a subscription plan by its ID.
    """

    return db.get(Plan, plan_id)
