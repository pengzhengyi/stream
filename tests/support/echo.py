"""The echo extension point: a test point whose requests tell the provider how to misbehave."""

import itertools
import os
import sys
import threading
import time
from datetime import timedelta
from typing import Literal, Protocol

from pydantic import BaseModel

from medleyplay.plugin_api import AuthError, ExtensionPoint, NetworkError


class Say(BaseModel):
    """Say `text` back, after doing whatever else the request asks for."""

    text: str
    sleep_seconds: float = 0
    crash: bool = False
    print_text: bool = False
    raises: Literal["network", "auth", "value", "exit"] | None = None
    wrong_reply: bool = False
    count_calls: bool = False
    exit_after_seconds: float | None = None


class Said(BaseModel):
    """What the provider said; `calls` counts its calls in this process, when asked to."""

    text: str
    calls: int = 0


class Echo(Protocol):
    """A provider that says things back."""

    def say(self, request: Say) -> Said:
        """Say the request's text back."""
        ...


ECHO = ExtensionPoint[Echo]("echo")
SAY = ECHO.operation("say", Say, Said, lambda echo: echo.say, deadline=timedelta(seconds=2))
SAY_QUICKLY = ECHO.operation(
    "say_quickly", Say, Said, lambda echo: echo.say, deadline=timedelta(seconds=0.5)
)


class Parrot:
    """An echo provider that does exactly what each request asks."""

    def __init__(self) -> None:
        self._calls = itertools.count(1)

    def say(self, request: Say) -> Said:
        """Say the text back, misbehaving first as the request asks."""
        time.sleep(request.sleep_seconds)
        if request.print_text:
            sys.stdout.write(f"{request.text}\n")
            sys.stdout.flush()
        if request.crash:
            os._exit(3)
        if request.exit_after_seconds is not None:
            threading.Timer(request.exit_after_seconds, os._exit, args=(5,)).start()
        match request.raises:
            case "network":
                raise NetworkError(request.text)
            case "auth":
                raise AuthError(request.text)
            case "value":
                raise ValueError(request.text)
            case "exit":
                raise SystemExit(request.text)
            case None:
                pass
        if request.wrong_reply:
            return Say(text=request.text)  # type: ignore[return-value] # a plugin that breaks its contract
        return Said(text=request.text, calls=next(self._calls) if request.count_calls else 0)
