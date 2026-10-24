"""The composition root: settings from the environment, and the app wired from them."""

import contextlib
import os
import socket
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import Engine

from medleyplay.application import Clock
from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.throttle import SignInThrottle
from medleyplay.persistence.database import database_url, make_engine, make_sessionmaker, migrate
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services

DEFAULT_PORT: Final = 8000
DATA_DIR_VARIABLE: Final = "MEDLEYPLAY_DATA_DIR"
ALLOWED_HOSTS_VARIABLE: Final = "MEDLEYPLAY_ALLOWED_HOSTS"


@dataclass(frozen=True)
class Settings:
    """Where the server keeps its data, and which host names it answers to."""

    data_dir: Path
    allowed_hosts: tuple[str, ...]

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> "Settings":
        """Read the settings from environment variables, falling back to defaults.

        `MEDLEYPLAY_DATA_DIR` overrides the data folder. `MEDLEYPLAY_ALLOWED_HOSTS`
        adds comma-separated host names, such as a router's DNS name for the server.
        """
        configured = environ.get(DATA_DIR_VARIABLE)
        data_dir = Path(configured) if configured else default_data_dir(environ)
        extra = tuple(h.strip() for h in environ.get(ALLOWED_HOSTS_VARIABLE, "").split(",") if h)
        return cls(data_dir=data_dir, allowed_hosts=(*local_host_names(), *extra))


def default_data_dir(environ: Mapping[str, str], platform: str = sys.platform) -> Path:
    """Return the platform's folder for an application's data."""
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "medleyplay"
    xdg = environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "medleyplay"


def local_host_names() -> tuple[str, ...]:
    """Return the names and addresses LAN devices may use to reach this machine."""
    hostname = socket.gethostname()
    names = {"localhost", "127.0.0.1", "::1", hostname, f"{hostname.removesuffix('.local')}.local"}
    # An unresolvable hostname still leaves the names above.
    with contextlib.suppress(OSError):
        names.update(socket.gethostbyname_ex(hostname)[2])
    names.update(_primary_address())
    return tuple(sorted(names))


def _primary_address() -> set[str]:
    # Connecting a UDP socket sends nothing; it only asks the OS which address it
    # would route from.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))  # TEST-NET-1: never a real host
        except OSError:
            return set()
        return {str(probe.getsockname()[0])}


def utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


def open_database(data_dir: Path) -> Engine:
    """Open the database in `data_dir`, creating the folder and migrating the schema."""
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    engine = make_engine(database_url(data_dir))
    migrate(engine)
    return engine


def build_services(engine: Engine, clock: Clock = utc_now) -> Services:
    """Return the services over the database `engine` opens."""
    units = make_sessionmaker(engine)
    hasher = PasswordHash((Argon2Hasher(),))
    return Services(
        accounts=AccountService(units, hasher, clock, SignInThrottle(clock)),
        catalog=CatalogService(units, clock),
    )


def build_app(settings: Settings) -> FastAPI:
    """Return the server's app for `settings`; it closes the database when it shuts down."""
    engine = open_database(settings.data_dir)

    @asynccontextmanager
    async def close_database_on_shutdown(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    return create_app(
        build_services(engine), settings.allowed_hosts, lifespan=close_database_on_shutdown
    )


def environment() -> Mapping[str, str]:
    """Return the process environment; a seam so tests never read the real one."""
    return os.environ
