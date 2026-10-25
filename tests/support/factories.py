"""Object Mothers: one factory per type the suites build."""

from medleyplay.application.accounts import NewAccount
from medleyplay.domain.accounts import Account, AccountId, Role, Username
from medleyplay.domain.catalog import SourceKey, TrackDetails

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
