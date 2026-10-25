"""Create the plugin state table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "plugin_state",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("faulted_at", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
        sa.Column("fault_reason", sa.String(length=2048), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_plugin_state")),
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("plugin_state")
