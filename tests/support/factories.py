"""Object Mothers: one factory per type the suites build."""

from ipaddress import IPv4Network

from medleyplay.application.accounts import NewAccount
from medleyplay.domain.accounts import Account, AccountId, Role, Username
from medleyplay.domain.catalog import SourceKey, TrackDetails
from medleyplay.domain.mode import Network, NetworkKind
from medleyplay.plugin_api import Tags
from medleyplay.programs.info_json import InfoChapter, InfoText
from medleyplay.programs.scan_library import InfoJson, ScannedFile

PASSWORD = "correct horse battery"


class NewAccountFactory:
    """Builds the details an admin enters for a new Account."""

    @staticmethod
    def admin(username: str = "alice") -> NewAccount:
        """Return Alice, the household's admin, unless another username is given."""
        return NewAccount(username, username.title(), PASSWORD, Role.ADMIN)

    @staticmethod
    def member(username: str = "bob") -> NewAccount:
        """Return Bob, a member, unless another username is given."""
        return NewAccount(username, username.title(), PASSWORD, Role.MEMBER)


class AccountFactory:
    """Builds Accounts that exist only in memory, for checks that need no database."""

    @staticmethod
    def admin(account_id: int = 98) -> Account:
        """Return an admin Account."""
        return Account(AccountId(account_id), Username("admin"), "Admin", Role.ADMIN)

    @staticmethod
    def member(account_id: int = 99) -> Account:
        """Return a member Account."""
        return Account(AccountId(account_id), Username("member"), "Member", Role.MEMBER)


class SourceKeyFactory:
    """Builds Source keys."""

    @staticmethod
    def bilibili(video: str = "BV1Xx41117Tz", part: int = 1) -> SourceKey:
        """Return the key of one part of a Bilibili video."""
        return SourceKey("bilibili", f"{video}/p{part}")


class TrackDetailsFactory:
    """Builds the details a Source reports about its music."""

    @staticmethod
    def song(title: str = "Intro") -> TrackDetails:
        """Return a three-minute song by a fixed artist."""
        return TrackDetails(title=title, artist="The Band", album="Blue", duration_ms=180_000)


class InfoJsonFactory:
    """Builds what a scan reports of the `.info.json` beside an audio file."""

    @staticmethod
    def read(
        title: str = "【初音ミク】メルト / ryo(supercell)【MV】",
        description: str = "",
        chapters: tuple[InfoChapter, ...] = (),
        *,
        modified_ns: int = 1,
    ) -> InfoJson:
        """Return a sidecar the scan read, saying `title`, which names a song and its artist."""
        text = InfoText(title=title, description=description, chapters=chapters)
        return InfoJson(size=200, modified_ns=modified_ns, text=text)

    @staticmethod
    def unchanged(*, modified_ns: int = 1) -> InfoJson:
        """Return a sidecar the scan listed but skipped, since it hasn't changed."""
        return InfoJson(size=200, modified_ns=modified_ns)

    @staticmethod
    def wordless() -> InfoJson:
        """Return a sidecar the scan read that has no title, description, or chapters.

        ```json
        {"id": "BV1dm4y1s7ak", "title": "", "chapters": []}
        ```
        """
        return InfoJson(size=200, modified_ns=1, text=InfoText())

    @staticmethod
    def malformed(*, modified_ns: int = 1) -> InfoJson:
        """Return a sidecar the scan couldn't read, as one cut short mid-object would be."""
        error = "isn't valid JSON (JSONDecodeError)"
        return InfoJson(size=200, modified_ns=modified_ns, error=error)


class ScannedFileFactory:
    """Builds the files a Library scan reports."""

    @staticmethod
    def song(
        path: str = "Blue/01 Intro.wav",
        title: str = "Intro",
        *,
        fingerprint: str = "",
        info_json: InfoJson | None = None,
    ) -> ScannedFile:
        """Return a new or changed file whose tags were read, fingerprinted by its path."""
        return ScannedFile(
            path=path,
            size=1000,
            modified_ns=1,
            changed=True,
            fingerprint=fingerprint or f"1000:{path}",
            tags=Tags(title=title, artist="The Band", album="Blue", duration_ms=180_000),
            info_json=info_json,
        )

    @staticmethod
    def untagged(
        path: str = "BV1dm4y1s7ak.m4a", *, fingerprint: str = "", info_json: InfoJson | None = None
    ) -> ScannedFile:
        """Return a new or changed file whose tags said nothing, as a video download's do."""
        return ScannedFile(
            path=path,
            size=1000,
            modified_ns=1,
            changed=True,
            fingerprint=fingerprint or f"1000:{path}",
            tags=Tags(),
            info_json=info_json,
        )

    @staticmethod
    def unchanged(
        path: str = "Blue/01 Intro.wav", *, info_json: InfoJson | None = None
    ) -> ScannedFile:
        """Return a file the scan skipped because it hasn't changed."""
        return ScannedFile(path=path, size=1000, modified_ns=1, changed=False, info_json=info_json)


class NetworkFactory:
    """Builds the networks the server finds itself on."""

    @staticmethod
    def home_wifi(router: str | None = "a2:b3:c4:d5:e6:f7") -> Network:
        """The household's Wi-Fi: router `192.168.31.1`, at `a2:b3:c4:d5:e6:f7`, on a /24.

        With `router=None`, the router's hardware address couldn't be read.
        """
        return Network(NetworkKind.WIFI, IPv4Network("192.168.31.0/24"), router)

    @staticmethod
    def iphone_hotspot() -> Network:
        """An iPhone's Personal Hotspot: router `172.20.10.1`, on the iPhone's usual /28."""
        return Network(NetworkKind.WIFI, IPv4Network("172.20.10.0/28"), "02:0f:c4:d5:e6:07")
