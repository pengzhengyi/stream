"""Add the Mode's setting and the metered networks.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-27 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "mode_setting",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_mode_setting_single")),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_mode_setting_revision")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mode_setting")),
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("mode_setting")
