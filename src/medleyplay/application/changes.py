"""Change notices: services say what changed after they commit, and the policy hears it."""

import threading
from collections.abc import Callable

type OnChange = Callable[[str], None]
"""Told what changed, such as `settings`, after the change is committed."""


class Changes:
    """Where services say what changed; every listener hears each notice, on the caller's thread."""

    def __init__(self) -> None:
        """Create a hub with no listeners."""
        self._lock = threading.Lock()
        self._listeners: list[OnChange] = []

    def listen(self, listener: OnChange) -> None:
        """Tell `listener` of every change from now on."""
        with self._lock:
            self._listeners.append(listener)

    def tell(self, what: str) -> None:
        """Tell every listener that `what` changed."""
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            listener(what)
