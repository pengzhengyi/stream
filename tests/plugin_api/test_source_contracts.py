"""The Source contract kits catch resolvers, downloaders, and specs that break them."""

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from medleyplay.plugin_api import (
    AudioQuality,
    Canonical,
    Canonicalize,
    CheckedLogin,
    CheckLogin,
    Downloaded,
    DownloadPart,
    PartDetails,
    ReadVideo,
    VideoDetails,
    VideoStatus,
)
from medleyplay.plugin_api.testing import (
    ContractError,
    check_credential_spec,
    check_source_downloader,
    check_source_resolver,
)

VIDEO = "BV1Xx41117Tz"
LINK = f"https://www.bilibili.com/video/{VIDEO}"
HIGH = AudioQuality(id="30280", label="192 kbps", kbps=192)


def _readable(*parts: int) -> VideoDetails:
    """A video with the given parts, readable at one quality."""
    return VideoDetails(
        title="Song",
        uploader="Uploader",
        parts=tuple(PartDetails(part=part, title=f"Part {part}") for part in parts),
        qualities=(HIGH,),
    )


@dataclass
class Resolver:
    canonical: Canonical = field(default_factory=lambda: Canonical(video=VIDEO, link=LINK))
    details: VideoDetails = field(default_factory=lambda: _readable(1))

    def canonicalize(self, request: Canonicalize) -> Canonical:
        return self.canonical

    def read(self, request: ReadVideo) -> VideoDetails:
        return self.details


def test_a_resolver_that_keeps_the_contract_returns_the_video_and_its_details() -> None:
    canonical, details = check_source_resolver(Resolver(), LINK)

    assert canonical.video == VIDEO
    assert details == _readable(1)


def test_a_link_to_no_video_has_no_details() -> None:
    resolver = Resolver(canonical=Canonical(video=None, link=LINK))

    assert check_source_resolver(resolver, LINK) == (resolver.canonical, None)


@pytest.mark.parametrize(
    "resolver",
    [
        Resolver(canonical=Canonical(video=None, part=2, link=LINK)),
        Resolver(details=_readable(1, 1)),
        Resolver(details=_readable()),
        Resolver(details=_readable(1).model_copy(update={"qualities": ()})),
        Resolver(details=_readable(1).model_copy(update={"qualities": (HIGH, HIGH)})),
        Resolver(details=_readable(1).model_copy(update={"status": VideoStatus.GONE})),
    ],
    ids=[
        "a part of no video",
        "a part twice",
        "no parts",
        "no qualities",
        "a quality twice",
        "a gone video with parts",
    ],
)
def test_a_resolver_that_breaks_the_contract_is_caught(resolver: Resolver) -> None:
    with pytest.raises(ContractError):
        check_source_resolver(resolver, LINK)


@dataclass
class Downloader:
    name: str | None = "song.m4a"
    gone: bool = False
    quality: str | None = "30280"

    def download(self, request: DownloadPart) -> Downloaded:
        if self.name is not None and not self.name.startswith("/"):
            (Path(request.folder) / Path(self.name).name).write_bytes(b"audio")
        return Downloaded(file=self.name, gone=self.gone, quality=self.quality)


def _request(folder: Path) -> DownloadPart:
    return DownloadPart(video=VIDEO, part=1, quality="best", folder=str(folder))


def test_a_downloader_that_keeps_the_contract_names_its_file(tmp_path: Path) -> None:
    assert check_source_downloader(Downloader(), _request(tmp_path)).file == "song.m4a"


def test_a_part_that_is_gone_has_no_file(tmp_path: Path) -> None:
    downloader = Downloader(name=None, gone=True, quality=None)

    assert check_source_downloader(downloader, _request(tmp_path)).gone


@pytest.mark.parametrize(
    "downloader",
    [
        Downloader(name="sub/song.m4a"),
        Downloader(name="/music/song.m4a"),
        Downloader(name=None),
        Downloader(gone=True),
        Downloader(quality=None),
    ],
    ids=["a path", "an absolute path", "no file and not gone", "a file and gone", "no quality"],
)
def test_a_downloader_that_breaks_the_contract_is_caught(
    downloader: Downloader, tmp_path: Path
) -> None:
    with pytest.raises(ContractError):
        check_source_downloader(downloader, _request(tmp_path))


def test_a_file_behind_a_link_is_caught(tmp_path: Path) -> None:
    (tmp_path / "elsewhere.m4a").write_bytes(b"audio")
    folder = tmp_path / "job"
    folder.mkdir()
    (folder / "song.m4a").symlink_to(tmp_path / "elsewhere.m4a")

    class Linker:
        def download(self, request: DownloadPart) -> Downloaded:
            return Downloaded(file="song.m4a", quality="30280")

    with pytest.raises(ContractError):
        check_source_downloader(Linker(), _request(folder))


@dataclass
class Spec:
    kept: str = "SESSDATA=1"
    valid: bool = True
    drifts: bool = False

    def check(self, request: CheckLogin) -> CheckedLogin:
        login = request.text + "!" if self.drifts else self.kept
        return CheckedLogin(valid=self.valid, login=login if self.valid or self.drifts else "")


def test_a_spec_that_keeps_the_contract_keeps_its_login_unchanged_when_checked_again() -> None:
    assert check_credential_spec(Spec(), "cookies").login == "SESSDATA=1"


def test_a_login_that_is_not_valid_keeps_nothing() -> None:
    assert check_credential_spec(Spec(valid=False), "cookies").login == ""


@pytest.mark.parametrize(
    "spec", [Spec(drifts=True), Spec(valid=False, drifts=True)], ids=["drifts", "invalid keeps"]
)
def test_a_spec_that_breaks_the_contract_is_caught(spec: Spec) -> None:
    with pytest.raises(ContractError):
        check_credential_spec(spec, "cookies")
