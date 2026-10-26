"""Add each Account's preferences, starting with its keyboard shortcuts.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "preference",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_preference_revision")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_preference_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("pk_preference")),
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("preference")
