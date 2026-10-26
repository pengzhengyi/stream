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

from medleyplay.persistence.database import MIGRATIONS, database_url, make_engine, migrate
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


_FAVORITE = {"field": "favorite", "op": "is", "value": True}


def _migrate_to(engine: Engine, revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
