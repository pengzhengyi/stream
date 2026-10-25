"""The built-in Library plugins, a Job runner, and the Library and playback services."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.catalog import CatalogService
from medleyplay.application.job_runner import JobRunner
from medleyplay.application.jobs import AnyJobKind, JobService
from medleyplay.application.libraries import LibraryService, scan_library_kind
from medleyplay.application.playback import PlaybackService, cache_source_kind
from medleyplay.application.plugins import Lineup, PluginService
from medleyplay.domain.jobs import JobId, JobState, JobView
from medleyplay.plugin_host.client import PluginHost
from medleyplay.plugin_host.loader import plugin_names
from tests.support.fakes import FakeClock

LIBRARY_PLUGINS = ("fsspec-library", "tinytag-tags")


@dataclass(frozen=True)
class Libraries:
    """A running Library service, with the plugins, Jobs, catalog, and playback around it."""

    service: LibraryService
    plugins: PluginService
    jobs: JobService
    catalog: CatalogService
    playback: PlaybackService

    def wait_for(self, job_id: JobId, *states: JobState) -> JobView:
        """Wait until the Job is in one of `states`, and return it."""
        ends = time.monotonic() + 30
        while time.monotonic() < ends:
            view = self.jobs.get_job(job_id)
            if view.job.state in states:
                return view
            time.sleep(0.05)
        message = f"Job {job_id} is {self.jobs.get_job(job_id).job.state}, not in {states}."
        raise AssertionError(message)


@contextmanager
def running_libraries(
    units: sessionmaker[Session], clock: FakeClock, data_dir: Path
) -> Iterator[Libraries]:
    """Run the Library plugins, the scan and cache Job kinds, and the services over `data_dir`."""
    lineup = Lineup(plugin_names(), LIBRARY_PLUGINS)
    plugins = PluginService(units, clock, lineup, PluginHost(LIBRARY_PLUGINS))
    scan, cache = scan_library_kind(clock), cache_source_kind(data_dir)
    kinds: dict[str, AnyJobKind] = {scan.name: scan, cache.name: cache}
    runner = JobRunner(units, clock, kinds, plugins, data_dir / "jobs", poll=timedelta(seconds=0.1))
    jobs = JobService(units, clock, kinds, runner)
    plugins.start()
    jobs.start()
    try:
        yield Libraries(
            LibraryService(units, clock, plugins, jobs, scan, data_dir),
            plugins,
            jobs,
            CatalogService(units, clock),
            PlaybackService(units, plugins, jobs, cache, data_dir),
        )
    finally:
        jobs.stop()
        plugins.close()
