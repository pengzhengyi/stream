"""Create the download table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "download",
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=64), nullable=False),
        sa.Column("quality", sa.String(length=32), nullable=False),
        sa.Column("backend", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("downloaded_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.CheckConstraint("size >= 0", name=op.f("ck_download_size")),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source.id"],
            name=op.f("fk_download_source_id_source"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_download")),
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("download")
