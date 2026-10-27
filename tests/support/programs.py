"""A test Job program, and Job kinds that run it, whose requests ask it to misbehave."""

import os
import subprocess  # nosec B404 -- starts `sleep`, to show a Job's children die with it
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from medleyplay.application.jobs import JobKind
from medleyplay.domain.jobs import Job
from medleyplay.plugin_host.job import JobContext, JobProgram, PluginCallFailedError
from tests.support.echo import SAY, Say


class EchoJob(BaseModel):
    """Echo `text` back, after doing whatever else the request asks for."""

    text: str
    steps: int = 0
    step_seconds: float = 0
    say: Say | None = None
    """Ask the plugin `parrot` to say this, and echo its reply instead."""
    catch_failure: bool = False
    fail: Literal["raise", "crash", "hang", "sleeping-child"] | None = None


class Echoed(BaseModel):
    """What the Job echoed."""

    text: str


def run(request: EchoJob, context: JobContext) -> Echoed:
    """Echo the request's text, misbehaving first as it asks."""
    for step in range(1, request.steps + 1):
        context.report(step / request.steps, f"Step {step}")
        time.sleep(request.step_seconds)
    text = request.text
    if request.say is not None:
        try:
            text = context.call(SAY, "parrot", request.say).text
        except PluginCallFailedError:
            if not request.catch_failure:
                raise
            text = "caught"
    match request.fail:
        case "raise":
            raise ValueError(text)
        case "crash":
            os._exit(9)
        case "hang":
            time.sleep(3600)
        case "sleeping-child":
            child = subprocess.Popen(["sleep", "60"])  # noqa: S607 -- a test of process groups
            context.report(message=str(child.pid))
            time.sleep(3600)
        case None:
            pass
    return Echoed(text=text)


ECHO: JobProgram[EchoJob, Echoed] = JobProgram(EchoJob, Echoed, run)


def echo_kind(
    completed: list[str],
    *,
    idle_timeout: timedelta = timedelta(seconds=20),
    complete: Callable[[Session, Job, Echoed], None] | None = None,
    needs_network: bool = False,
) -> JobKind[EchoJob, Echoed]:
    """Return the kind `echo`, whose completion appends each Job's echo to `completed`.

    With `needs_network`, it stands for a kind that contacts a site, as a download does.
    """

    def record(db: Session, job: Job, result: Echoed) -> None:
        completed.append(result.text)

    return JobKind(
        name="echo",
        program="tests.support.programs:ECHO",
        request=EchoJob,
        result=Echoed,
        complete=complete or record,
        points=("echo",),
        idle_timeout=idle_timeout,
        needs_network=needs_network,
    )
