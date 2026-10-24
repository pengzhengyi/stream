"""Command-line entry point: `python -m stream`."""

import argparse
from collections.abc import Sequence

from stream import __version__


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line and return the process exit code."""
    parser = argparse.ArgumentParser(
        prog="stream",
        description="Play music on your local network.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
