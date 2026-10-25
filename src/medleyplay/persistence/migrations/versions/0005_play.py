"""Create the play table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "play",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("played_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_play_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"], ["track.id"], name=op.f("fk_play_track_id_track"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("account_id", "id", name=op.f("pk_play")),
    )
    op.create_index(op.f("ix_play_track_id"), "play", ["track_id"], unique=False)


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index(op.f("ix_play_track_id"), table_name="play")
    op.drop_table("play")
