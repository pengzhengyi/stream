"""Add smart playlists, the Keep downloaded switch, Download use times, and the settings.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.add_column("playlist", sa.Column("rules", sa.JSON(), nullable=True))
    op.add_column(
        "playlist",
        sa.Column("keep_downloaded", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "download",
        sa.Column("last_served_at", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
    )
    op.add_column(
        "download",
        sa.Column("last_wanted_at", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
    )
    op.create_table(
        "setting",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_setting_single")),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_setting_revision")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_setting")),
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("setting")
    with op.batch_alter_table("download") as batch:
        batch.drop_column("last_wanted_at")
        batch.drop_column("last_served_at")
    with op.batch_alter_table("playlist") as batch:
        batch.drop_column("keep_downloaded")
        batch.drop_column("rules")
