"""Fixtures every suite shares: a migrated database, the services, and an API client."""

from collections.abc import Iterator
from pathlib import Path

import hypothesis
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.downloads import DownloadService, download_source_kind
from medleyplay.application.events import JobEvents
from medleyplay.application.job_runner import JobRunner
from medleyplay.application.jobs import AnyJobKind, JobService
from medleyplay.application.libraries import LibraryService, scan_library_kind
from medleyplay.application.linked_accounts import LinkedAccountService
from medleyplay.application.links import LinkService
from medleyplay.application.playback import PlaybackService, cache_source_kind
from medleyplay.application.plugins import Lineup, PluginService
from medleyplay.application.policy import PolicyService
from medleyplay.application.preferences import PreferencesService
from medleyplay.application.settings import SettingsService
from medleyplay.application.throttle import SignInThrottle
from medleyplay.persistence.database import database_url, make_engine, make_sessionmaker, migrate
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services
from tests.support.fakes import FakeClock, MemorySecrets

TEST_HOST = "testserver"

# The suites run in parallel processes, so a busy machine slows each example and
# its generation; the properties check what the code does, not how fast.
hypothesis.settings.register_profile(
    "medleyplay", deadline=None, suppress_health_check=[hypothesis.HealthCheck.too_slow]
)
hypothesis.settings.load_profile("medleyplay")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def units(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(database_url(tmp_path))
    migrate(engine)
    yield make_sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def hasher() -> PasswordHash:
    # The cheapest Argon2id parameters: the tests check behavior, not hash strength.
    return PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1),))


@pytest.fixture
def accounts(
    units: sessionmaker[Session], hasher: PasswordHash, clock: FakeClock
) -> AccountService:
    # Several Accounts on, so the suites can exercise roles and members; the
    # one-Account default has its own tests.
    return AccountService(units, hasher, clock, SignInThrottle(clock), multiple_accounts=True)


@pytest.fixture
def changes() -> list[str]:
    """What the services said changed, in order."""
    return []


@pytest.fixture
def catalog(units: sessionmaker[Session], clock: FakeClock, changes: list[str]) -> CatalogService:
    return CatalogService(units, clock, changes.append)


@pytest.fixture
def settings(units: sessionmaker[Session], clock: FakeClock, changes: list[str]) -> SettingsService:
    return SettingsService(units, clock, changes.append)


@pytest.fixture
def preferences(units: sessionmaker[Session], clock: FakeClock) -> PreferencesService:
    return PreferencesService(units, clock)


@pytest.fixture
def plugins(units: sessionmaker[Session], clock: FakeClock) -> PluginService:
    # No plugins and no host; suites that need plugins start a host of test plugins.
    return PluginService(units, clock, Lineup(), host=None)


@pytest.fixture
def jobs(
    units: sessionmaker[Session], clock: FakeClock, plugins: PluginService, tmp_path: Path
) -> JobService:
    # A runner that isn't started; suites that run Jobs start their own.
    scan, cache = scan_library_kind(clock), cache_source_kind(tmp_path / "data")
    download = download_source_kind(tmp_path / "data", tmp_path / "jobs", clock)
    kinds: dict[str, AnyJobKind] = {scan.name: scan, cache.name: cache, download.name: download}
    runner = JobRunner(units, clock, kinds, plugins, tmp_path / "jobs")
    return JobService(units, clock, kinds, runner)


@pytest.fixture
def libraries(
    units: sessionmaker[Session],
    clock: FakeClock,
    plugins: PluginService,
    jobs: JobService,
    tmp_path: Path,
) -> LibraryService:
    return LibraryService(units, clock, plugins, jobs, scan_library_kind(clock), tmp_path / "data")


@pytest.fixture
def downloads(
    units: sessionmaker[Session],
    clock: FakeClock,
    plugins: PluginService,
    jobs: JobService,
    linked: LinkedAccountService,
    tmp_path: Path,
) -> DownloadService:
    data_dir = tmp_path / "data"
    kind = download_source_kind(data_dir, tmp_path / "jobs", clock)
    return DownloadService(units, plugins, jobs, kind, linked, data_dir, clock)


@pytest.fixture
def playback(
    units: sessionmaker[Session],
    plugins: PluginService,
    jobs: JobService,
    downloads: DownloadService,
    tmp_path: Path,
) -> PlaybackService:
    data_dir = tmp_path / "data"
    return PlaybackService(units, plugins, jobs, cache_source_kind(data_dir), data_dir, downloads)


@pytest.fixture
def links(
    units: sessionmaker[Session],
    clock: FakeClock,
    plugins: PluginService,
    catalog: CatalogService,
    downloads: DownloadService,
) -> LinkService:
    return LinkService(units, clock, plugins, catalog, downloads)


@pytest.fixture
def policy(
    units: sessionmaker[Session],
    clock: FakeClock,
    downloads: DownloadService,
    plugins: PluginService,
    tmp_path: Path,
) -> PolicyService:
    # Not started: the suites evaluate when they mean to. The server always has its
    # data folder, whose disk the policy measures.
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    return PolicyService(units, clock, downloads, plugins, data_dir)


@pytest.fixture
def secrets() -> MemorySecrets:
    return MemorySecrets()


@pytest.fixture
def linked(
    units: sessionmaker[Session], clock: FakeClock, plugins: PluginService, secrets: MemorySecrets
) -> LinkedAccountService:
    return LinkedAccountService(units, clock, plugins, secrets)


@pytest.fixture
def services(  # noqa: PLR0913, PLR0917 -- one argument per service
    accounts: AccountService,
    catalog: CatalogService,
    plugins: PluginService,
    jobs: JobService,
    libraries: LibraryService,
    playback: PlaybackService,
    linked: LinkedAccountService,
    links: LinkService,
    settings: SettingsService,
    policy: PolicyService,
    preferences: PreferencesService,
) -> Services:
    """The services of a server with no plugins on; a suite replaces what it runs for real."""
    return Services(
        accounts=accounts,
        catalog=catalog,
        plugins=plugins,
        jobs=jobs,
        libraries=libraries,
        playback=playback,
        linked=linked,
        links=links,
        events=JobEvents(),
        settings=settings,
        policy=policy,
        preferences=preferences,
    )


@pytest.fixture
def client(services: Services, tmp_path: Path) -> Iterator[TestClient]:
    # No client is built there, so the suites never depend on a local build.
    app = create_app(services, allowed_hosts=[TEST_HOST], client_dir=tmp_path / "client")
    with TestClient(app, base_url=f"http://{TEST_HOST}") as test_client:
        yield test_client
