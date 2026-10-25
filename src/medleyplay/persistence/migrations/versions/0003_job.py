"""Create the job table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = "state IN ('waiting', 'queued', 'running')"


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("interruptions", sa.Integer(), nullable=False),
        sa.Column("not_before", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("failure_kind", sa.String(length=16), nullable=True),
        sa.Column("failure_message", sa.String(length=2048), nullable=False),
        sa.Column("created_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.Column("started_at", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
        sa.Column("finished_at", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
        sa.CheckConstraint(
            "state IN ('waiting', 'queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_job_state"),
        ),
        sa.CheckConstraint("attempts >= 0 AND interruptions >= 0", name=op.f("ck_job_counts")),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["account.id"],
            name=op.f("fk_job_requested_by_account"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
    )
    op.create_index(
        "ix_job_active_target",
        "job",
        ["kind", "target"],
        unique=True,
        sqlite_where=sa.text(ACTIVE),
    )
    op.create_index("ix_job_state", "job", ["state"], unique=False)


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index("ix_job_state", table_name="job")
    op.drop_index("ix_job_active_target", table_name="job")
    op.drop_table("job")
