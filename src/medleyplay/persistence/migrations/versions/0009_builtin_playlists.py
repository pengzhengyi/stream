"""Mark the Playlists the server keeps for each Account, starting with Favorites.

An Account that already has a smart playlist of exactly its favorites keeps it as
its Favorites, the oldest if it has several, rather than gaining a second one; the
server makes Favorites for every other Account when it starts.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    with op.batch_alter_table("playlist") as batch:
        batch.add_column(sa.Column("builtin", sa.String(length=32), nullable=True))
    op.create_index(
        "ix_playlist_account_builtin", "playlist", ["account_id", "builtin"], unique=True
    )
    playlist = sa.table(
        "playlist",
        sa.column("id", sa.Uuid()),
        sa.column("account_id", sa.Integer()),
        sa.column("rules", sa.JSON()),
        sa.column("builtin", sa.String()),
        sa.column("created_at", sa.String()),
    )
    connection = op.get_bind()
    adopted: set[int] = set()
    rows = connection.execute(
        sa.select(playlist.c.id, playlist.c.account_id, playlist.c.rules)
        .where(playlist.c.rules.is_not(None))
        .order_by(playlist.c.created_at, playlist.c.id)
    )
    for playlist_id, account_id, rules in rows.all():
        if account_id not in adopted and _only_favorites(rules):
            adopted.add(account_id)
            connection.execute(
                sa.update(playlist).where(playlist.c.id == playlist_id).values(builtin="favorites")
            )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index("ix_playlist_account_builtin", table_name="playlist")
    with op.batch_alter_table("playlist") as batch:
        batch.drop_column("builtin")


def _only_favorites(rules: object) -> bool:
    """Return whether a stored rules document matches exactly the favorite Tracks."""
    if not isinstance(rules, dict):
        return False
    conditions = rules.get("conditions")
    if not isinstance(conditions, list) or len(conditions) != 1:
        return False
    [condition] = conditions
    return (
        isinstance(condition, dict)
        and condition.get("field") == "favorite"
        and condition.get("op") == "is"
        and condition.get("value") is True
        and not condition.get("negate", False)
    )
