"""Create the catalog and account tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-24 23:41:27.441233
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "account",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'member')", name=op.f("ck_account_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account")),
        sa.UniqueConstraint("username", name=op.f("uq_account_username")),
    )
    op.create_table(
        "track",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("artist", sa.String(length=512), nullable=False),
        sa.Column("album", sa.String(length=512), nullable=False),
        sa.Column("album_artist", sa.String(length=512), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("added_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_track")),
    )
    op.create_table(
        "playlist",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.Column("updated_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_playlist_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playlist")),
    )
    with op.batch_alter_table("playlist", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_playlist_account_id"), ["account_id"], unique=False)

    op.create_table(
        "session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.Column("last_seen_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_session_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_session_token_hash")),
    )
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_session_account_id"), ["account_id"], unique=False)

    op.create_table(
        "source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("locator", sa.String(length=2048), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "state IN ('ok', 'missing', 'unavailable', 'cant_play')", name=op.f("ck_source_state")
        ),
        sa.ForeignKeyConstraint(
            ["track_id"], ["track.id"], name=op.f("fk_source_track_id_track"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source")),
        sa.UniqueConstraint("kind", "locator", name="uq_source_kind_locator"),
    )
    with op.batch_alter_table("source", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_source_track_id"), ["track_id"], unique=False)

    op.create_table(
        "track_state",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("play_count", sa.Integer(), nullable=False),
        sa.Column("last_played_at", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
        sa.CheckConstraint("play_count >= 0", name=op.f("ck_track_state_play_count")),
        sa.CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5", name=op.f("ck_track_state_rating")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_track_state_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["track.id"],
            name=op.f("fk_track_state_track_id_track"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "track_id", name=op.f("pk_track_state")),
    )
    with op.batch_alter_table("track_state", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_track_state_track_id"), ["track_id"], unique=False)

    op.create_table(
        "playlist_entry",
        sa.Column("playlist_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["playlist_id"],
            ["playlist.id"],
            name=op.f("fk_playlist_entry_playlist_id_playlist"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["track.id"],
            name=op.f("fk_playlist_entry_track_id_track"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("playlist_id", "position", name=op.f("pk_playlist_entry")),
    )
    with op.batch_alter_table("playlist_entry", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_playlist_entry_track_id"), ["track_id"], unique=False)


def downgrade() -> None:
    """Revert this revision."""
    with op.batch_alter_table("playlist_entry", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_playlist_entry_track_id"))

    op.drop_table("playlist_entry")
    with op.batch_alter_table("track_state", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_track_state_track_id"))

    op.drop_table("track_state")
    with op.batch_alter_table("source", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_source_track_id"))

    op.drop_table("source")
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_session_account_id"))

    op.drop_table("session")
    with op.batch_alter_table("playlist", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_playlist_account_id"))

    op.drop_table("playlist")
    op.drop_table("track")
    op.drop_table("account")
