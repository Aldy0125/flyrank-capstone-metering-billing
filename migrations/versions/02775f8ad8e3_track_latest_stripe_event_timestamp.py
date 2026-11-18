"""Track the latest Stripe event timestamp per subscription."""

from alembic import op
import sqlalchemy as sa


revision = "02775f8ad8e3"
down_revision = "5a5f984af0ed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "last_stripe_event_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "subscriptions",
        "last_stripe_event_created_at",
    )
