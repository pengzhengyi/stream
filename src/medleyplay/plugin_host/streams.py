"""Keeping standard input and output for the protocol, out of plugins' reach."""

import os
import sys
from pathlib import Path
from typing import IO


def take_standard_streams() -> tuple[IO[str], IO[str]]:
    """Return private copies of standard input and output for the protocol.

    Afterwards a plugin that reads standard input gets end of file, and anything it
    prints goes to standard error.
    """
    protocol_in = os.fdopen(os.dup(0), "r", encoding="utf-8")
    protocol_out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    os.dup2(2, 1)
    sys.stdin = Path(os.devnull).open(encoding="utf-8")  # noqa: SIM115 -- open for the process's life
    sys.stdout = sys.stderr
    return protocol_in, protocol_out
