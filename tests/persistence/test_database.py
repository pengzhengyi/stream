"""The database: migrations match the schema, and every connection is configured."""

from datetime import datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.persistence.database import database_url, make_engine, migrate
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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"


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
