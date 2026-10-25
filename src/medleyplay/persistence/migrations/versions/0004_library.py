"""Create the library table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "library",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=4096), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("added_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.Column("last_scanned_at", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
        sa.CheckConstraint("kind IN ('folder', 'zip')", name=op.f("ck_library_kind")),
        sa.CheckConstraint("state IN ('online', 'offline')", name=op.f("ck_library_state")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library")),
        sa.UniqueConstraint("kind", "path", name="uq_library_kind_path"),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("library")
