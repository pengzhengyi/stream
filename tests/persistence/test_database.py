"""The database: migrations match the schema, and every connection is configured."""

import json
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.persistence.database import (
    MIGRATIONS,
    MigrationError,
    database_url,
    make_engine,
    migrate,
)
from medleyplay.persistence.schema import Base, UtcDateTime


def test_the_migrations_build_exactly_the_schema_the_code_declares(tmp_path: Path) -> None:
    engine = make_engine(database_url(tmp_path))
    migrate(engine)

    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert differences == []


def test_migrating_a_current_database_again_changes_nothing(
    units: sessionmaker[Session],
) -> None:
    engine = units.kw["bind"]

    migrate(engine)

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == _head()


def _head() -> str | None:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    return ScriptDirectory.from_config(config).get_current_head()


@pytest.mark.parametrize(
    ("pragma", "expected"), [("foreign_keys", 1), ("busy_timeout", 5000), ("journal_mode", "wal")]
)
def test_every_connection_to_a_file_database_is_configured(
    units: sessionmaker[Session], pragma: str, expected: object
) -> None:
    with units() as db:
        assert db.scalar(text(f"PRAGMA {pragma}")) == expected


def test_an_in_memory_database_keeps_its_default_journal() -> None:
    engine = make_engine("sqlite://")

    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA journal_mode")) == "memory"
    engine.dispose()


def test_a_naive_datetime_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="naive"):
        UtcDateTime().process_bind_param(datetime(2026, 1, 1), make_engine("sqlite://").dialect)  # noqa: DTZ001 -- the naive value is the input under test


def test_migrating_keeps_an_accounts_oldest_smart_playlist_of_favorites_as_its_favorites(
    tmp_path: Path,
) -> None:
    engine = make_engine(database_url(tmp_path))
    _migrate_to(engine, "0008")
    favorites = {"version": 1, "match": "all", "conditions": [_FAVORITE]}
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO account (id, username, display_name, password_hash, role, created_at)"
                " VALUES (1, 'alice', 'Alice', 'x', 'admin', '2026-10-01 00:00:00.000000')"
            )
        )
        for name, rules, created in [
            ("Hearts", favorites, "2026-10-02"),
            ("Favorites", favorites, "2026-10-03"),
            (
                "Not favorites",
                {**favorites, "conditions": [{**_FAVORITE, "negate": True}]},
                "2026-10-01",
            ),
            ("Road trip", None, "2026-10-01"),
        ]:
            connection.execute(
                text(
                    "INSERT INTO playlist (id, account_id, name, rules, keep_downloaded,"
                    " created_at, updated_at) VALUES (:id, 1, :name, :rules, 0, :at, :at)"
                ),
                {
                    "id": uuid.uuid4().hex,
                    "name": name,
                    "rules": None if rules is None else json.dumps(rules),
                    "at": f"{created} 00:00:00.000000",
                },
            )

    migrate(engine)

    with engine.connect() as connection:
        marked = connection.execute(
            text("SELECT name, builtin FROM playlist WHERE builtin IS NOT NULL")
        ).all()
    engine.dispose()
    assert marked == [("Hearts", "favorites")]


def test_migrating_records_each_tracks_values_with_the_origin_they_most_likely_had(
    tmp_path: Path,
) -> None:
    engine = make_engine(database_url(tmp_path))
    _migrate_to(engine, "0011")
    with engine.begin() as connection:
        for track_id, title, artist, kind, locator in [
            (1, "Night Drive", "Blue Room", "library", "1/Albums/01 Intro.flac"),
            (2, "BV1dm4y1s7ak", "", "library", "2/BV1dm4y1s7ak.m4a"),
            (3, "Mixtape", "Blue Room", "bilibili", "BV17x411w7KC/p1"),
        ]:
            connection.execute(
                text(
                    "INSERT INTO track (id, title, artist, album, album_artist, added_at)"
                    " VALUES (:id, :title, :artist, '', '', '2026-10-01 00:00:00.000000')"
                ),
                {"id": track_id, "title": title, "artist": artist},
            )
            connection.execute(
                text(
                    "INSERT INTO source (track_id, kind, locator, state, details)"
                    " VALUES (:id, :kind, :locator, 'ok', '{}')"
                ),
                {"id": track_id, "kind": kind, "locator": locator},
            )

    migrate(engine)

    with engine.connect() as connection:
        values = connection.execute(
            text("SELECT track_id, field, origin, value FROM track_value ORDER BY 1, 2, 3")
        ).all()
    engine.dispose()
    assert [
        (track, field, origin, json.loads(value)) for track, field, origin, value in values
    ] == [
        (1, "artist", "files", "Blue Room"),
        (1, "title", "file_name", "01 Intro"),
        (1, "title", "files", "Night Drive"),
        (2, "title", "file_name", "BV1dm4y1s7ak"),
        (3, "artist", "video", "Blue Room"),
        (3, "title", "video", "Mixtape"),
    ]


def test_a_migration_refused_for_broken_references_leaves_the_database_as_it_was(
    tmp_path: Path,
) -> None:
    engine = make_engine(database_url(tmp_path))
    _migrate_to(engine, "0011")
    with engine.connect() as connection:
        # A Source of a Track that is gone: only a database edited by hand could hold one.
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        connection.execute(
            text(
                "INSERT INTO source (track_id, kind, locator, state, details)"
                " VALUES (99, 'library', '1/Gone.flac', 'ok', '{}')"
            )
        )
        connection.commit()

    with pytest.raises(MigrationError, match="1 broken reference"):
        migrate(engine)

    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        columns = {row.name for row in connection.execute(text("PRAGMA table_info(track)"))}
    engine.dispose()
    assert (version, "track_number" in columns) == ("0011", False)


_FAVORITE = {"field": "favorite", "op": "is", "value": True}


def _migrate_to(engine: Engine, revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
