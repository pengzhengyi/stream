"""Keep each detail of a Track with its origin, and add track numbers, years, and genres.

Today's values are recorded with the origin they most likely had: a Library
Track's title is its `file_name` when it is the file's name and from its `files`
otherwise, its other values are from its `files`, and a site Track's are the
`video`'s. Every Library Track also keeps its file's name as a `file_name` title.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-27 20:30:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TEXT = ("title", "artist", "album", "album_artist")


def upgrade() -> None:
    """Apply this revision."""
    with op.batch_alter_table("track") as batch:
        batch.add_column(sa.Column("track_number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("disc_number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("year", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("genre", sa.String(length=512), nullable=False, server_default="")
        )
    with op.batch_alter_table("track") as batch:
        batch.alter_column("genre", server_default=None)
    op.create_table(
        "track_value",
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("recorded_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["track.id"],
            name=op.f("fk_track_value_track_id_track"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("track_id", "field", "origin", name=op.f("pk_track_value")),
    )
    _record_todays_values()


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("track_value")
    with op.batch_alter_table("track") as batch:
        batch.drop_column("genre")
        batch.drop_column("year")
        batch.drop_column("disc_number")
        batch.drop_column("track_number")


def _record_todays_values() -> None:
    connection = op.get_bind()
    library_paths: dict[int, str] = {}
    for track_id, locator in connection.execute(
        sa.text("SELECT track_id, locator FROM source WHERE kind = 'library' ORDER BY id")
    ):
        library_paths.setdefault(track_id, str(locator).partition("/")[2])
    # Stored as the schema stores a UTC instant: without its offset.
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
    rows = []
    for track in connection.execute(
        sa.text("SELECT id, title, artist, album, album_artist FROM track")
    ).mappings():
        path = library_paths.get(track["id"])
        if path is not None and track["title"] != PurePosixPath(path).stem:
            rows.append(
                {
                    "track_id": track["id"],
                    "field": "title",
                    "origin": "file_name",
                    "value": PurePosixPath(path).stem,
                }
            )
        for field in _TEXT:
            value = track[field]
            if not value:
                continue
            if path is None:
                origin = "video"
            elif field == "title" and value == PurePosixPath(path).stem:
                origin = "file_name"
            else:
                origin = "files"
            rows.append({"track_id": track["id"], "field": field, "origin": origin, "value": value})
    for row in rows:
        connection.execute(
            sa.text(
                "INSERT INTO track_value (track_id, field, origin, value, recorded_at)"
                " VALUES (:track_id, :field, :origin, json_quote(:value), :now)"
            ),
            {**row, "now": now},
        )
