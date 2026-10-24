"""The application: the commands and queries the web layer and the command line call."""

from collections.abc import Callable
from datetime import datetime

type Clock = Callable[[], datetime]
"""Return the current instant as an aware UTC datetime."""
