"""Keep the songs inside an album file, each a stretch of the file played as its own Track.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-31 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "segment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("album_source_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("artist", sa.String(length=512), nullable=False),
        sa.Column("split_length_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["album_source_id"],
            ["source.id"],
            name=op.f("fk_segment_album_source_id_source"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["track.id"],
            name=op.f("fk_segment_track_id_track"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_segment")),
        sa.UniqueConstraint("track_id", name=op.f("uq_segment_track_id")),
    )
    with op.batch_alter_table("segment") as batch:
        batch.create_index(batch.f("ix_segment_album_source_id"), ["album_source_id"], unique=False)


def downgrade() -> None:
    """Revert this revision."""
    with op.batch_alter_table("segment") as batch:
        batch.drop_index(batch.f("ix_segment_album_source_id"))
    op.drop_table("segment")
