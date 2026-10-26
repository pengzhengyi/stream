"""The composition root: settings from the environment and the config file, and the app."""

import contextlib
import fcntl
import os
import socket
import sys
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
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
from medleyplay.application.changes import Changes
from medleyplay.application.downloads import DownloadService, download_source_kind
from medleyplay.application.events import JobEvents
from medleyplay.application.job_runner import JobProcesses, JobRunner
from medleyplay.application.jobs import AnyJobKind, JobService
from medleyplay.application.libraries import LibraryService, scan_library_kind
from medleyplay.application.linked_accounts import LinkedAccountService
from medleyplay.application.links import LinkService
from medleyplay.application.playback import PlaybackService, cache_source_kind
from medleyplay.application.plugins import Lineup, PluginService
from medleyplay.application.policy import PolicyService
from medleyplay.application.secrets import KeychainSecrets, Secrets
from medleyplay.application.settings import SettingsService
from medleyplay.application.throttle import SignInThrottle
from medleyplay.config import CONFIG_FILE, Config, load_config
from medleyplay.persistence.database import database_url, make_engine, make_sessionmaker, migrate
from medleyplay.plugin_host.client import HostCommand, PluginHost
from medleyplay.plugin_host.loader import BUILT_IN_PLUGINS, plugin_names
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services

DEFAULT_PORT: Final = 8000
JOBS_FOLDER: Final = "jobs"
INSTANCE_LOCK: Final = "server.lock"
DATA_DIR_VARIABLE: Final = "MEDLEYPLAY_DATA_DIR"
ALLOWED_HOSTS_VARIABLE: Final = "MEDLEYPLAY_ALLOWED_HOSTS"


@dataclass(frozen=True)
class Settings:
    """Where the server keeps its data, which host names it answers to, and safe mode.

    Everything else is in the config file in the data folder.
    """

    data_dir: Path
    allowed_hosts: tuple[str, ...]
    safe_mode: bool = False

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


@dataclass(frozen=True)
class PluginSource:
    """Where plugins come from, and how to start the host that runs them."""

    package: str = BUILT_IN_PLUGINS
    command: HostCommand = field(default_factory=HostCommand)


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


def build_services(  # noqa: PLR0913 -- the database and folder, then settings with defaults
    engine: Engine,
    data_dir: Path,
    clock: Clock = utc_now,
    *,
    config: Config = Config(),  # noqa: B008 -- a frozen value
    safe_mode: bool = False,
    source: PluginSource = PluginSource(),  # noqa: B008 -- a frozen value
    kinds: Mapping[str, AnyJobKind] | None = None,
    secrets: Secrets | None = None,
) -> Services:
    """Return the services over the database in `data_dir`, configured by `config`.

    `kinds` are the Job kinds the server runs; Jobs keep their working folders in
    `jobs` in the data folder. Logins are kept in `secrets`, by default the Keychain.
    Every change the download policy depends on, and every Job's change of state,
    asks it to evaluate.
    """
    units = make_sessionmaker(engine)
    changes = Changes()
    hasher = PasswordHash((Argon2Hasher(),))
    available = plugin_names(source.package)
    enabled = () if safe_mode else config.enabled_plugins(available)
    lineup = Lineup(available, enabled, config.unknown_plugins(available), safe_mode)
    host = PluginHost(enabled, package=source.package, command=source.command) if enabled else None
    plugins = PluginService(units, clock, lineup, host, changes.tell)
    linked = LinkedAccountService(units, clock, plugins, secrets or KeychainSecrets(), changes.tell)
    scan = scan_library_kind(clock)
    cache = cache_source_kind(data_dir)
    download = download_source_kind(data_dir, data_dir / JOBS_FOLDER, clock)
    job_kinds: dict[str, AnyJobKind] = {
        scan.name: scan,
        cache.name: cache,
        download.name: download,
        **(kinds or {}),
    }
    processes = JobProcesses(source.command, source.package)
    events = JobEvents()
    runner = JobRunner(
        units,
        clock,
        job_kinds,
        plugins,
        data_dir / JOBS_FOLDER,
        processes=processes,
        logins=linked,
        events=events,
    )
    jobs = JobService(units, clock, job_kinds, runner, events)
    catalog = CatalogService(units, clock, changes.tell)
    # A database from before built-in Playlists, or a restored one, gains them now.
    catalog.ensure_builtin_playlists()
    downloads = DownloadService(units, plugins, jobs, download, linked, data_dir, clock)
    policy = PolicyService(units, clock, downloads, plugins, data_dir)
    changes.listen(policy.request)
    events.listen(policy.request)
    return Services(
        accounts=AccountService(
            units,
            hasher,
            clock,
            SignInThrottle(clock),
            multiple_accounts=config.multiple_accounts,
            on_change=changes.tell,
        ),
        catalog=catalog,
        plugins=plugins,
        jobs=jobs,
        libraries=LibraryService(units, clock, plugins, jobs, scan, data_dir),
        playback=PlaybackService(units, plugins, jobs, cache, data_dir, downloads),
        linked=linked,
        links=LinkService(units, clock, plugins, catalog, downloads),
        events=events,
        settings=SettingsService(units, clock, changes.tell),
        policy=policy,
    )


def build_app(settings: Settings, source: PluginSource = PluginSource()) -> FastAPI:  # noqa: B008 -- a frozen value
    """Return the server's app for `settings`.

    The app starts the plugin host, removes stale cache copies, and starts the Job
    runner and the download policy, which evaluates at once, when it starts; it
    stops them and closes the database when it shuts down. A config file that
    doesn't parse raises `ConfigError`; another server using the same data folder
    raises `AlreadyRunningError` as the app starts.
    """
    config = load_config(settings.data_dir / CONFIG_FILE)
    engine = open_database(settings.data_dir)
    services = build_services(
        engine, settings.data_dir, config=config, safe_mode=settings.safe_mode, source=source
    )

    @asynccontextmanager
    async def run_in_background(_: FastAPI) -> AsyncIterator[None]:
        try:
            with hold_instance_lock(settings.data_dir):
                services.plugins.start()
                services.playback.sweep_cache()
                services.playback.sweep_downloads()
                services.jobs.start()
                services.policy.start()
                try:
                    yield
                finally:
                    services.policy.stop()
                    services.jobs.stop()
                    services.plugins.close()
        finally:
            engine.dispose()

    return create_app(services, settings.allowed_hosts, lifespan=run_in_background)


class AlreadyRunningError(Exception):
    """Another server is using this data folder."""


@contextmanager
def hold_instance_lock(data_dir: Path) -> Iterator[None]:
    """Hold the data folder's server lock, so a second server can't run Jobs on it too."""
    with (data_dir / INSTANCE_LOCK).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            message = f"Another medleyplay server is using {data_dir}."
            raise AlreadyRunningError(message) from None
        yield


def environment() -> Mapping[str, str]:
    """Return the process environment; a seam so tests never read the real one."""
    return os.environ
