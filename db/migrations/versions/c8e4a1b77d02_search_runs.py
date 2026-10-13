"""search_runs

Revision ID: c8e4a1b77d02
Revises: 21760b9caa40
Create Date: 2026-10-13 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8e4a1b77d02"
down_revision: str | Sequence[str] | None = "21760b9caa40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_simulations", sa.Integer(), nullable=False),
        sa.Column("best_policy_id", sa.Uuid(), nullable=True),
        sa.Column("best_objective", sa.Float(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed', 'superseded')",
            name="ck_search_runs_status",
        ),
        sa.ForeignKeyConstraint(["best_policy_id"], ["policies.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_search_runs_job", "search_runs", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_search_runs_job", table_name="search_runs")
    op.drop_table("search_runs")
