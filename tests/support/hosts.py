"""Plugin hosts and plugin services that load the test plugins in `tests.support.plugins`."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Final

from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.plugins import Lineup, PluginService
from medleyplay.plugin_host.client import MEMORY_LIMIT, HostCommand, PluginHost
from medleyplay.plugin_host.loader import plugin_names

TEST_PLUGINS: Final = "tests.support.plugins"
# A host imports the test plugins from the repository, so it needs the root on its path.
TEST_COMMAND: Final = HostCommand(env={"PYTHONPATH": str(Path(__file__).resolve().parents[2])})
# Long enough for a cold start on a busy test machine; the hanging plugin costs this once.
TEST_LOAD_DEADLINE: Final = timedelta(seconds=4)


def host_of(*plugins: str, memory_limit: int = MEMORY_LIMIT) -> PluginHost:
    """Return a host, not yet started, that loads the test `plugins`."""
    return PluginHost(
        plugins,
        package=TEST_PLUGINS,
        command=TEST_COMMAND,
        load_deadline=TEST_LOAD_DEADLINE,
        memory_limit=memory_limit,
    )


@contextmanager
def started_host(*plugins: str, memory_limit: int = MEMORY_LIMIT) -> Iterator[PluginHost]:
    """Start a host loading the test `plugins`, and stop it afterwards."""
    host = host_of(*plugins, memory_limit=memory_limit)
    host.start()
    try:
        yield host
    finally:
        host.close()


@contextmanager
def started_plugins(
    units: sessionmaker[Session],
    clock: Clock,
    *enabled: str,
    unknown: tuple[str, ...] = (),
    safe_mode: bool = False,
) -> Iterator[PluginService]:
    """Start a plugin service over the test plugins with `enabled` on, and stop it afterwards.

    Every test plugin is available; those not in `enabled` are off.
    """
    on = () if safe_mode else enabled
    lineup = Lineup(plugin_names(TEST_PLUGINS), on, unknown, safe_mode)
    service = PluginService(units, clock, lineup, host_of(*on) if on else None)
    service.start()
    try:
        yield service
    finally:
        service.close()
