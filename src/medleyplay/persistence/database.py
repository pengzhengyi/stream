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


class MigrationError(Exception):
    """A migration left rows that refer to rows no longer there."""


def migrate(engine: Engine) -> None:
    """Bring the database's schema up to the newest migration; a no-op when it is current.

    Foreign keys are off while it runs: SQLite alters a table by building a new one
    and dropping the old, and the drop would otherwise delete every row that refers
    to it. The whole upgrade is one transaction, its table changes included, and it
    commits only once every reference still holds; otherwise the database is left
    as it was.
    """
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    with engine.connect() as connection:
        # The pragma does nothing inside a transaction, so it is set before one begins.
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        connection.commit()
        driver = connection.connection.driver_connection
        if not isinstance(driver, SQLiteConnection):
            message = "medleyplay migrates only SQLite databases."
            raise TypeError(message)
        # By default the driver commits before each table change; without its own
        # transaction control, the BEGIN below holds the table changes too.
        isolation = driver.isolation_level
        driver.isolation_level = None
        try:
            with connection.begin():
                connection.exec_driver_sql("BEGIN")
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                broken = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
                if broken:
                    message = f"The migration left {len(broken)} broken references."
                    raise MigrationError(message)
        finally:
            driver.isolation_level = isolation
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()
