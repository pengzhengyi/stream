"""The test plugin `tube` answering for `bilibili`, with real download Jobs and the services."""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.catalog import CatalogService
from medleyplay.application.downloads import DownloadService, download_source_kind
from medleyplay.application.job_runner import JobProcesses, JobRunner
from medleyplay.application.jobs import AnyJobKind, JobService
from medleyplay.application.linked_accounts import LinkedAccountService
from medleyplay.application.links import LinkService
from medleyplay.application.playback import PlaybackService, cache_source_kind
from medleyplay.application.plugins import PluginService
from medleyplay.domain.jobs import JobId, JobState, JobView
from tests.support.fakes import FakeClock, MemorySecrets
from tests.support.hosts import TEST_COMMAND, TEST_PLUGINS, started_plugins

WAIT: float = 20


@dataclass(frozen=True)
class Site:
    """The services around a running `tube` plugin, and the folders they keep files in."""

    links: LinkService
    downloads: DownloadService
    playback: PlaybackService
    linked: LinkedAccountService
    catalog: CatalogService
    jobs: JobService
    plugins: PluginService
    secrets: MemorySecrets
    data_dir: Path

    def wait_for(
        self, job_id: JobId, *states: JobState, until: Callable[[JobView], bool] | None = None
    ) -> JobView:
        """Wait until the Job is in one of `states`, and `until` holds, then return it."""
        ends = time.monotonic() + WAIT
        while time.monotonic() < ends:
            view = self.jobs.get_job(job_id)
            if view.job.state in states and (until is None or until(view)):
                return view
            time.sleep(0.05)
        message = f"Job {job_id} is {self.jobs.get_job(job_id).job.state}, not in {states}."
        raise AssertionError(message)


@contextmanager
def running_site(
    units: sessionmaker[Session], clock: FakeClock, data_dir: Path, secrets: MemorySecrets
) -> Iterator[Site]:
    """Run `tube`, download Jobs, and the link, download, and playback services over `data_dir`."""
    jobs_dir = data_dir / "jobs"
    download = download_source_kind(data_dir, jobs_dir, clock)
    cache = cache_source_kind(data_dir)
    kinds: dict[str, AnyJobKind] = {download.name: download, cache.name: cache}
    with started_plugins(units, clock, "tube") as plugins:
        linked = LinkedAccountService(units, clock, plugins, secrets)
        runner = JobRunner(
            units,
            clock,
            kinds,
            plugins,
            jobs_dir,
            processes=JobProcesses(TEST_COMMAND, TEST_PLUGINS),
            poll=timedelta(seconds=0.1),
            logins=linked,
        )
        jobs = JobService(units, clock, kinds, runner)
        catalog = CatalogService(units, clock)
        downloads = DownloadService(units, plugins, jobs, download, linked, data_dir)
        jobs.start()
        try:
            yield Site(
                links=LinkService(units, clock, plugins, catalog, downloads),
                downloads=downloads,
                playback=PlaybackService(units, plugins, jobs, cache, data_dir, downloads),
                linked=linked,
                catalog=catalog,
                jobs=jobs,
                plugins=plugins,
                secrets=secrets,
                data_dir=data_dir,
            )
        finally:
            jobs.stop()
