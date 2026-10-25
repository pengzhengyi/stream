"""Command-line entry point: `python -m medleyplay`."""

import argparse
import dataclasses
import getpass
import sys
from collections.abc import Callable, Sequence

from medleyplay import __version__
from medleyplay.config import CONFIG_FILE, ConfigError, load_config
from medleyplay.domain.errors import MedleyplayError
from medleyplay.server import (
    DEFAULT_PORT,
    Settings,
    build_app,
    build_services,
    environment,
    open_database,
)

type ReadPassword = Callable[[str], str]


def main(
    argv: Sequence[str] | None = None,
    *,
    serve: Callable[[Settings, str, int], None] | None = None,
    read_password: ReadPassword = getpass.getpass,
) -> int:
    """Parse the command line, run the command, and return the process exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    settings = Settings.from_environment(environment())
    try:
        match args.command:
            case "serve":
                settings = dataclasses.replace(settings, safe_mode=args.safe_mode)
                (serve or _run_server)(settings, args.host, args.port)
            case "reset-password":
                return _reset_password(settings, args.username, read_password)
    except ConfigError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="medleyplay",
        description="Play music on your local network.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="run the server")
    # Every interface by default: devices on the LAN must reach it.
    serve.add_argument("--host", default="0.0.0.0", help="address to listen on")  # noqa: S104  # nosec B104
    serve.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to listen on")
    serve.add_argument(
        "--safe-mode", action="store_true", help="start with every plugin off, for this run"
    )
    reset = commands.add_parser(
        "reset-password", help="set an Account's password and sign it out everywhere"
    )
    reset.add_argument("username")
    return parser


def _run_server(settings: Settings, host: str, port: int) -> None:  # pragma: no cover
    import uvicorn  # noqa: PLC0415 -- only `serve` needs the server

    uvicorn.run(build_app(settings), host=host, port=port)


def _reset_password(settings: Settings, username: str, read_password: ReadPassword) -> int:
    password = read_password("New password: ")
    if read_password("Repeat it: ") != password:
        sys.stderr.write("The passwords don't match; nothing changed.\n")
        return 1
    config = load_config(settings.data_dir / CONFIG_FILE)
    engine = open_database(settings.data_dir)
    try:
        build_services(engine, config=config).accounts.reset_password(username, password)
    except MedleyplayError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    finally:
        engine.dispose()
    sys.stdout.write(f"Changed the password of {username!r} and signed it out everywhere.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
