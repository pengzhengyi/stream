"""The SQLite engine, its connection settings, and running migrations."""

from pathlib import Path
from sqlite3 import Connection as SQLiteConnection
from typing import Final

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

BUSY_TIMEOUT_MS: Final = 5_000
MIGRATIONS: Final = "medleyplay.persistence:migrations"


def database_url(data_dir: Path) -> str:
    """Return the URL of the database inside the data folder."""
    return f"sqlite:///{data_dir / 'medleyplay.sqlite3'}"


def make_engine(url: str) -> Engine:
    """Return an engine whose every connection enforces foreign keys and waits on locks.

    A file database also switches to write-ahead logging, so readers never block the
    one writer.
    """
    engine = create_engine(url, connect_args={"check_same_thread": False})
    uses_file = engine.url.database not in {None, "", ":memory:"}

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection: SQLiteConnection, _: ConnectionPoolEntry) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        if uses_file:
            cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    return engine


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    """Return a factory for units of work on the engine."""
    return sessionmaker(engine, expire_on_commit=False)


def migrate(engine: Engine) -> None:
    """Bring the database's schema up to the newest migration; a no-op when it is current."""
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
