"""The household's settings, shared by every Account and changed by an admin."""

from dataclasses import dataclass
from enum import StrEnum


class RemovalOrder(StrEnum):
    """Which Download the policy removes first when it must make room."""

    LEAST_FAVORITE = "least_favorite"


@dataclass(frozen=True)
class Settings:
    """The settings, and the revision they were read at; revision 0 was never saved.

    `storage_limit` is the most bytes Downloads and cache copies may use, or
    `None` for no limit, so nothing is removed.
    """

    storage_limit: int | None = None
    removal_order: RemovalOrder = RemovalOrder.LEAST_FAVORITE
    revision: int = 0
