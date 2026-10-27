"""Downloads: starting the Job that downloads a site's Source, and recording what it made.

The program checks the file the plugin made, in the Job's folder; the completion
renames it into `downloads/` and records it, in the transaction that ends the
Job. A crash between the two leaves a file no row names, which the sweep at
startup removes, and the Job runs again.
"""

from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Final

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.jobs import JobKind, JobService
from medleyplay.application.linked_accounts import LinkedAccountService
from medleyplay.application.plugins import PluginService
from medleyplay.domain.accounts import Account, AccountId
from medleyplay.domain.catalog import SourceId, SourceState
from medleyplay.domain.downloads import (
    DOWNLOAD_EXTENSIONS,
    DOWNLOADS_FOLDER,
    MAX_DOWNLOAD_BYTES,
    download_name,
    download_target,
)
from medleyplay.domain.errors import NotFoundError
from medleyplay.domain.jobs import Job, JobState
from medleyplay.domain.links import BILIBILI_SOURCE, parse_part_locator
from medleyplay.persistence.schema import DownloadRow, SourceRow
from medleyplay.plugin_api import BEST_QUALITY, SOURCE_DOWNLOADER
from medleyplay.programs.download_source import (
    DOWNLOAD_FOLDER,
    DownloadedSource,
    DownloadSource,
)

DOWNLOAD_KIND: Final = "download_source"
SERVED_EVERY: Final = timedelta(minutes=1)
"""How often a Download's last served time is written, since a player asks for many ranges."""
QUALITY_DETAIL: Final = "quality"
"""Where a site's Source keeps the quality its Downloads ask for, in its details."""

type DownloadKind = JobKind[DownloadSource, DownloadedSource]


def download_source_kind(data_dir: Path, jobs_dir: Path, clock: Clock) -> DownloadKind:
    """Return the Job kind that downloads a Bilibili Source into `downloads/` in `data_dir`.

    The Job uses the submitting Account's Bilibili login, when it has a valid one.
    """
    folder = data_dir / DOWNLOADS_FOLDER

    def complete(db: Session, job: Job, downloaded: DownloadedSource) -> None:
        source_id = SourceId(int(job.target.removeprefix("source:")))
        if downloaded.gone or downloaded.file is None:
            db.execute(
                update(SourceRow)
                .where(SourceRow.id == source_id)
                .values(state=SourceState.UNAVAILABLE)
            )
            return
        # The program checked the name; a completion trusts nothing a plugin said.
        if PurePosixPath(downloaded.file).name != downloaded.file:  # pragma: no cover
            raise ValueError(downloaded.file)
        name = download_name(source_id, downloaded.file)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        made = jobs_dir / str(job.id) / DOWNLOAD_FOLDER / downloaded.file
        made.replace(folder / name)
        row = db.get(DownloadRow, source_id) or DownloadRow(source_id=source_id)
        row.file_name = name
        row.quality = downloaded.quality
        row.backend = downloaded.backend
        row.size = downloaded.size
        row.downloaded_at = clock()
        db.add(row)

    return JobKind(
        name=DOWNLOAD_KIND,
        program="medleyplay.programs.download_source:DOWNLOAD_SOURCE",
        request=DownloadSource,
        result=DownloadedSource,
        complete=complete,
        points=(SOURCE_DOWNLOADER.name,),
        login_site=BILIBILI_SOURCE,
        needs_network=True,
    )


class DownloadService:
    """Start Downloads, and remove files no Download names."""

    def __init__(
        self,
        units: sessionmaker[Session],
        plugins: PluginService,
        jobs: JobService,
        kind: DownloadKind,
        linked: LinkedAccountService,
        data_dir: Path,
        clock: Clock,
    ) -> None:
        """Create a service keeping Downloads in `downloads/` in `data_dir`."""
        self._clock = clock
        self._units = units
        self._plugins = plugins
        self._jobs = jobs
        self._kind = kind
        self._linked = linked
        self.folder = data_dir / DOWNLOADS_FOLDER

    def start_for(self, account_id: AccountId, source_id: SourceId) -> Job | None:
        """Start downloading the Source for the policy, as `account_id`, even after a failure.

        As `start`, but a failed last download is tried again: the policy decides
        when that is due. A Source already downloaded, as one may be since the
        policy's snapshot, isn't downloaded again.
        """
        return self._start(account_id, source_id, retry_failed=True, skip_downloaded=True)

    def served(self, source_id: SourceId) -> None:
        """Record that the Source's Download was served now, at most once a minute.

        It reads before it writes, so the many range requests of one play don't
        each take the write lock.
        """
        now = self._clock()
        due = (DownloadRow.last_served_at.is_(None)) | (
            DownloadRow.last_served_at <= now - SERVED_EVERY
        )
        mine = DownloadRow.source_id == source_id
        with self._units() as db:
            if db.scalar(select(DownloadRow.source_id).where(mine, due)) is None:
                return
        with self._units.begin() as db:
            db.execute(update(DownloadRow).where(mine, due).values(last_served_at=now))

    def start(self, caller: Account, source_id: SourceId) -> Job | None:
        """Start downloading the Source, or return the Job already doing it.

        The Job uses the caller's login on the site when it is valid. An
        *unavailable* Source, or one no plugin that is on downloads, isn't
        downloaded: the answer is `None`. When the last download failed, the
        answer is that Job: the household retries it, so playing a Track again
        and again doesn't ask the site again and again.
        """
        return self._start(caller.id, source_id, retry_failed=False, skip_downloaded=False)

    def _start(
        self,
        account_id: AccountId,
        source_id: SourceId,
        *,
        retry_failed: bool,
        skip_downloaded: bool,
    ) -> Job | None:
        with self._units() as db:
            row = db.get(SourceRow, source_id)
            if row is None or row.kind != BILIBILI_SOURCE:
                message = f"The Source {source_id} isn't one medleyplay downloads."
                raise NotFoundError(message)
            if row.state == SourceState.UNAVAILABLE:
                return None
            if skip_downloaded and db.get(DownloadRow, source_id) is not None:
                return None
            video, part = parse_part_locator(row.locator)
            quality = str((row.details or {}).get(QUALITY_DETAIL, BEST_QUALITY))
            site = row.kind
        if site not in self._plugins.available_keys().get(SOURCE_DOWNLOADER.name, []):
            return None
        request = DownloadSource(
            site=site,
            video=video,
            part=part,
            quality=quality,
            extensions=DOWNLOAD_EXTENSIONS,
            max_bytes=MAX_DOWNLOAD_BYTES,
        )
        target = download_target(source_id)
        latest = self._jobs.latest(DOWNLOAD_KIND, target)
        if not retry_failed and latest is not None and latest.state is JobState.FAILED:
            return latest
        login = account_id if self._linked.has_valid(account_id, site) else None
        return self._jobs.submit(self._kind, target, request, account_id, login_account=login)

    def sweep(self) -> None:
        """Remove every file in `downloads/` that no Download names."""
        if not self.folder.is_dir():
            return
        with self._units() as db:
            named = set(db.scalars(select(DownloadRow.file_name)))
        for file in self.folder.iterdir():
            if file.name not in named:
                file.unlink(missing_ok=True)
