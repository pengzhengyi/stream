"""The tables. Alembic migrations create them; this module is the model they must match."""

import uuid
from datetime import UTC, datetime
from typing import override

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Dialect,
    ForeignKey,
    MetaData,
    String,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Constraint names are fixed so a later migration can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UtcDateTime(TypeDecorator[datetime]):
    """A UTC instant: stored without an offset, since SQLite drops it, and read back aware."""

    impl = DateTime
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            message = f"Refusing a naive datetime {value!r}; pass an aware UTC instant."
            raise ValueError(message)
        return value.astimezone(UTC).replace(tzinfo=None)

    @override
    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    """The declarative base every table derives from."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class AccountRow(Base):
    """An Account; `username` is stored in its canonical lowercase form."""

    __tablename__ = "account"
    __table_args__ = (CheckConstraint("role IN ('admin', 'member')", name="role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class SessionRow(Base):
    """A signed-in browser; only a SHA-256 hash of its token is kept."""

    __tablename__ = "session"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime)


class TrackRow(Base):
    """A piece of music."""

    __tablename__ = "track"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    artist: Mapped[str] = mapped_column(String(512), default="")
    album: Mapped[str] = mapped_column(String(512), default="")
    album_artist: Mapped[str] = mapped_column(String(512), default="")
    duration_ms: Mapped[int | None]
    added_at: Mapped[datetime] = mapped_column(UtcDateTime)


class SourceRow(Base):
    """Where a Track's audio comes from; `(kind, locator)` is its natural key."""

    __tablename__ = "source"
    __table_args__ = (
        UniqueConstraint("kind", "locator", name="uq_source_kind_locator"),
        CheckConstraint("state IN ('ok', 'missing', 'unavailable', 'cant_play')", name="state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("track.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    locator: Mapped[str] = mapped_column(String(2048))
    fingerprint: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16), default="ok")
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class TrackStateRow(Base):
    """One Account's favorite, rating, and play history for one Track."""

    __tablename__ = "track_state"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating"),
        CheckConstraint("play_count >= 0", name="play_count"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    track_id: Mapped[int] = mapped_column(
        ForeignKey("track.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    favorite: Mapped[bool] = mapped_column(default=False)
    rating: Mapped[int | None]
    play_count: Mapped[int] = mapped_column(default=0)
    last_played_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class PlaylistRow(Base):
    """An Account's Playlist; the id is chosen by the client, so creating it is retry-safe."""

    __tablename__ = "playlist"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class PlaylistEntryRow(Base):
    """One position in a Playlist."""

    __tablename__ = "playlist_entry"

    playlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playlist.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("track.id", ondelete="CASCADE"), index=True)
