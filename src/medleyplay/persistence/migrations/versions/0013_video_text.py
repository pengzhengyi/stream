"""Keep the text of a Track's video, as pasted or read beside the file.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-30 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "video_text",
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1_000), nullable=False),
        sa.Column("description", sa.String(length=20_000), nullable=False),
        sa.Column("chapters", sa.JSON(), nullable=False),
        sa.Column("came_from", sa.String(length=16), nullable=False),
        sa.Column("recorded_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.CheckConstraint(
            "came_from IN ('household', 'file')", name=op.f("ck_video_text_came_from")
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["track.id"],
            name=op.f("fk_video_text_track_id_track"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("track_id", name=op.f("pk_video_text")),
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("video_text")
