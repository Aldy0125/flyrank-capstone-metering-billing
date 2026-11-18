"""Create persistent background jobs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "6d0b2f9a4c71"
down_revision = "02775f8ad8e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_background_jobs_tenant_id_tenants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_background_jobs"),
    )

    op.create_index(
        "ix_background_jobs_tenant_created",
        "background_jobs",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_background_jobs_tenant_created",
        table_name="background_jobs",
    )
    op.drop_table("background_jobs")
