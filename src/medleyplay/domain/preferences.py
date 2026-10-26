"""An Account's preferences: its own choices for its pages, kept wherever it signs in."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Preferences:
    """An Account's preferences, and the revision they were read at; revision 0 was never saved.

    `shortcuts` gives each command the web client names its keys, written as the
    page writes them, such as `shift+right`; `None` leaves every command on the
    page's defaults. The server keeps them without knowing the commands, so a
    page with a new command needs no change here.
    """

    shortcuts: Mapping[str, tuple[str, ...]] | None = None
    revision: int = 0
