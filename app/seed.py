from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config.database import SessionLocal
from app.config.plan_catalog import DEFAULT_PLANS
from app.models.plan import Plan


def seed_plans() -> None:
    """
    Insert default subscription plans without creating duplicates.

    Existing plans are never overwritten automatically.
    Existing configurations are validated before commit.
    """

    plan_values = [
        {
            "id": plan.id,
            "api_call_limit": plan.api_call_limit,
            "ai_token_limit": plan.ai_token_limit,
            "monthly_price_cents": plan.monthly_price_cents,
            "currency": plan.currency,
            "is_active": plan.is_active,
        }
        for plan in DEFAULT_PLANS
    ]

    plan_ids = [plan.id for plan in DEFAULT_PLANS]

    # Insert plans and validate existing records atomically.
    with SessionLocal.begin() as session:

        statement = (
            pg_insert(Plan)
            .values(plan_values)
            .on_conflict_do_nothing(
                index_elements=[Plan.id]
            )
            .returning(Plan.id)
        )

        inserted_ids = set(
            session.scalars(statement).all()
        )

        # Retrieve all expected plans from the database.
        stored_plans = session.scalars(
            select(Plan).where(Plan.id.in_(plan_ids))
        ).all()

        stored_by_id = {
            plan.id: plan
            for plan in stored_plans
        }

        # Verify that existing configurations match the catalog.
        for definition in DEFAULT_PLANS:
            stored = stored_by_id.get(definition.id)

            if stored is None:
                raise RuntimeError(
                    f"Plan '{definition.id}' was not persisted."
                )

            expected_values = {
                "api_call_limit": definition.api_call_limit,
                "ai_token_limit": definition.ai_token_limit,
                "monthly_price_cents": definition.monthly_price_cents,
                "currency": definition.currency,
                "is_active": definition.is_active,
            }

            for field, expected in expected_values.items():
                actual = getattr(stored, field)

                if actual != expected:
                    raise RuntimeError(
                        f"Plan '{definition.id}' has an unexpected "
                        f"value for '{field}'. "
                        f"Expected: {expected!r}, "
                        f"actual: {actual!r}. "
                        "Existing data was not overwritten."
                    )

    # Display results after the transaction commits.
    for plan in DEFAULT_PLANS:
        if plan.id in inserted_ids:
            status = "INSERTED"
        else:
            status = "ALREADY EXISTS (unchanged)"

        print(f"Plan '{plan.id}': {status}")

    print(
        f"Plan seeding completed. "
        f"Total plans: {len(DEFAULT_PLANS)}, "
        f"Inserted: {len(inserted_ids)}"
    )


if __name__ == "__main__":
    seed_plans()
