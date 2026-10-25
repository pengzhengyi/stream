"""Fixtures every suite shares: a migrated database, the services, and an API client."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.job_runner import JobRunner
from medleyplay.application.jobs import JobService
from medleyplay.application.plugins import Lineup, PluginService
from medleyplay.application.throttle import SignInThrottle
from medleyplay.persistence.database import database_url, make_engine, make_sessionmaker, migrate
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services
from tests.support.fakes import FakeClock

TEST_HOST = "testserver"


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
def catalog(units: sessionmaker[Session], clock: FakeClock) -> CatalogService:
    return CatalogService(units, clock)


@pytest.fixture
def plugins(units: sessionmaker[Session], clock: FakeClock) -> PluginService:
    # No plugins and no host; suites that need plugins start a host of test plugins.
    return PluginService(units, clock, Lineup(), host=None)


@pytest.fixture
def jobs(
    units: sessionmaker[Session], clock: FakeClock, plugins: PluginService, tmp_path: Path
) -> JobService:
    # No Job kinds and a runner that isn't started; suites that run Jobs start their own.
    runner = JobRunner(units, clock, {}, plugins, tmp_path / "jobs")
    return JobService(units, clock, {}, runner)


@pytest.fixture
def client(
    accounts: AccountService, catalog: CatalogService, plugins: PluginService, jobs: JobService
) -> Iterator[TestClient]:
    app = create_app(Services(accounts, catalog, plugins, jobs), allowed_hosts=[TEST_HOST])
    with TestClient(app, base_url=f"http://{TEST_HOST}") as test_client:
        yield test_client
