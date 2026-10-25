"""The bilibili plugin's resolver, downloader, and login check, against made yt-dlp info."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from medleyplay.plugin_api import (
    AuthError,
    Canonicalize,
    CheckLogin,
    DownloadPart,
    NetworkError,
    ReadVideo,
    VideoStatus,
)
from medleyplay.plugin_api.progress import reporting_to
from medleyplay.plugin_api.testing import (
    check_credential_spec,
    check_source_downloader,
    check_source_resolver,
)
from medleyplay.plugins.bilibili import _ytdlp
from medleyplay.plugins.bilibili.providers import (
    BilibiliDownloader,
    BilibiliLogin,
    BilibiliResolver,
)
from tests.plugins.bilibili.infos import TITLE, UPLOADER, VIDEO, YtDlpInfoFactory

LINK = f"https://www.bilibili.com/video/{VIDEO}"


class Extractor:
    """A stand-in for yt-dlp's extraction: answers or raises by URL, keeping what was asked."""

    def __init__(self, answers: Mapping[str, Mapping[str, object] | Exception]) -> None:
        self.answers = answers
        self.asked: list[tuple[str, bool]] = []

    def __call__(self, url: str, *, playlist: bool) -> Mapping[str, object]:
        self.asked.append((url, playlist))
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _resolver(answers: Mapping[str, Mapping[str, object] | Exception]) -> BilibiliResolver:
    return BilibiliResolver(fetch=lambda _: LINK + "?p=2", extract=Extractor(answers))


def test_a_video_link_names_its_video_and_part() -> None:
    canonical = BilibiliResolver().canonicalize(Canonicalize(link=f"{LINK}?p=3"))

    assert (canonical.video, canonical.part, canonical.link) == (VIDEO, 3, f"{LINK}?p=3")


def test_a_short_link_is_followed_to_its_video() -> None:
    canonical = _resolver({}).canonicalize(Canonicalize(link="https://b23.tv/abc123"))

    assert (canonical.video, canonical.part, canonical.link) == (VIDEO, 2, f"{LINK}?p=2")


def test_a_short_link_off_bilibili_names_no_video_and_the_link_it_ended_on() -> None:
    resolver = BilibiliResolver(fetch=lambda _: "https://evil.example/video/BV1Xx41117Tz")

    canonical = resolver.canonicalize(Canonicalize(link="https://b23.tv/abc123"))

    assert (canonical.video, canonical.link) == (None, "https://evil.example/video/BV1Xx41117Tz")


def test_a_link_to_a_channel_names_no_video() -> None:
    canonical = BilibiliResolver().canonicalize(Canonicalize(link="https://www.bilibili.com/"))

    assert canonical.video is None


def test_a_video_with_one_part_reads_its_title_uploader_length_and_aac_qualities() -> None:
    details = _resolver({LINK: YtDlpInfoFactory.single()}).read(ReadVideo(video=VIDEO))

    assert (details.status, details.title, details.uploader) == (VideoStatus.OK, TITLE, UPLOADER)
    assert [(p.part, p.title, p.duration_ms) for p in details.parts] == [(1, TITLE, 200_500)]
    assert [q.id for q in details.qualities] == ["30280", "30232", "30216"]


def test_a_video_with_several_parts_reads_them_all_and_the_first_in_full() -> None:
    extractor = Extractor(
        {
            LINK: YtDlpInfoFactory.anthology(3),
            f"{LINK}?p=1": YtDlpInfoFactory.anthology_first_part(),
        }
    )

    details = BilibiliResolver(extract=extractor).read(ReadVideo(video=VIDEO))

    assert [(p.part, p.title) for p in details.parts] == [
        (1, "Intro"),
        (2, f"{TITLE} P2"),
        (3, f"{TITLE} P3"),
    ]
    assert extractor.asked == [(LINK, True), (f"{LINK}?p=1", False)]


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (_ytdlp.GoneError("This video may be deleted."), VideoStatus.GONE),
        (_ytdlp.NeedsLoginError("For premium members only."), VideoStatus.NEEDS_LOGIN),
    ],
)
def test_a_video_that_cant_be_read_says_why(failure: Exception, status: VideoStatus) -> None:
    details = _resolver({LINK: failure}).read(ReadVideo(video=VIDEO))

    assert (details.status, details.message, details.parts) == (status, str(failure), ())


def test_a_video_with_no_aac_audio_is_gone_naming_its_codecs() -> None:
    muxed = YtDlpInfoFactory.single(
        formats=[{"format_id": "16", "acodec": "mp4a", "vcodec": "avc1"}]
    )

    details = _resolver({LINK: muxed}).read(ReadVideo(video=VIDEO))

    assert details.status is VideoStatus.GONE
    assert "mp4a" in details.message


def test_a_network_failure_while_reading_stays_a_network_failure() -> None:
    with pytest.raises(NetworkError):
        _resolver({LINK: NetworkError("timed out")}).read(ReadVideo(video=VIDEO))


def test_the_resolver_keeps_the_contract() -> None:
    check_source_resolver(_resolver({LINK: YtDlpInfoFactory.single()}), LINK)


class Download:
    """A stand-in for yt-dlp's download: writes `audio.m4a`, reports progress, keeps its call."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def __call__(self, url: str, **options: object) -> Mapping[str, object]:
        self.calls.append({"url": url, **options})
        if self.failure is not None:
            raise self.failure
        on_progress = options["on_progress"]
        assert callable(on_progress)
        on_progress(500, 1000)
        on_progress(1000, None)
        path = Path(str(options["folder"])) / "audio.m4a"
        path.write_bytes(b"audio")
        return YtDlpInfoFactory.downloaded(str(path), format_id="30232")


def _part(folder: Path, quality: str = "best", login: str | None = None) -> DownloadPart:
    return DownloadPart(video=VIDEO, part=2, quality=quality, folder=str(folder), login=login)


def test_a_download_names_its_bare_file_and_the_quality_it_got(tmp_path: Path) -> None:
    downloaded = BilibiliDownloader(Download()).download(_part(tmp_path))

    assert (downloaded.file, downloaded.quality, downloaded.backend) == (
        "audio.m4a",
        "30232",
        "yt-dlp",
    )


def test_a_download_asks_for_its_quality_or_the_next_best_with_the_login(tmp_path: Path) -> None:
    download = Download()

    BilibiliDownloader(download).download(
        _part(tmp_path, "30232", login=str(tmp_path / "login.txt"))
    )

    call = download.calls[0]
    assert (call["url"], call["formats"], call["cookie_file"]) == (
        f"{LINK}?p=2",
        "30232/30216",
        str(tmp_path / "login.txt"),
    )


def test_the_best_quality_asks_for_every_aac_quality_best_first(tmp_path: Path) -> None:
    download = Download()

    BilibiliDownloader(download).download(_part(tmp_path))

    assert download.calls[0]["formats"] == "30280/30232/30216"


def test_a_download_reports_its_progress(tmp_path: Path) -> None:
    heard: list[float | None] = []

    with reporting_to(lambda fraction, _: heard.append(fraction)):
        BilibiliDownloader(Download()).download(_part(tmp_path))

    assert heard == [0.5, None]


def test_a_part_that_is_gone_has_no_file(tmp_path: Path) -> None:
    downloaded = BilibiliDownloader(Download(_ytdlp.GoneError("Removed."))).download(
        _part(tmp_path)
    )

    assert (downloaded.file, downloaded.gone, downloaded.message) == (None, True, "Removed.")


def test_a_part_that_needs_a_login_fails_as_a_login_failure(tmp_path: Path) -> None:
    downloader = BilibiliDownloader(Download(_ytdlp.NeedsLoginError("Members only.")))

    with pytest.raises(AuthError, match="needs a Bilibili login"):
        downloader.download(_part(tmp_path))


def test_the_downloader_keeps_the_contract(tmp_path: Path) -> None:
    check_source_downloader(BilibiliDownloader(Download()), _part(tmp_path))


COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".bilibili.com\tTRUE\t/\tTRUE\t1807142400\tSESSDATA\tabc%2C123\n"
    ".bilibili.com\tTRUE\t/\tFALSE\t1807142400\tbili_jct\tsecret-token\n"
)


def test_the_login_check_keeps_the_session_and_its_expiry() -> None:
    checked = check_credential_spec(BilibiliLogin(), COOKIES)

    assert checked.valid
    assert "SESSDATA" in checked.login
    assert "bili_jct" not in checked.login
    assert checked.expires_at is not None


def test_a_file_without_a_session_isnt_a_login() -> None:
    checked = BilibiliLogin().check(CheckLogin(text="# Netscape HTTP Cookie File\n"))

    assert (checked.valid, checked.login) == (False, "")
    assert "no Bilibili session" in checked.message
