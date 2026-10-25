"""The messages between the server and a Job process: one JSON object per line.

```text
server -> job  {"type": "job", "package": "medleyplay.plugins", "plugins": ["parrot"],
                "program": "tests.support.programs:ECHO", "request": {"text": "hi"},
                "work_dir": "/data/jobs/7"}
job -> server  {"type": "progress", "fraction": 0.5, "message": "Halfway", "peak_memory": 1}
job -> server  {"type": "finished", "outcomes": [], "peak_memory": 1}
```

A finished Job's result is in `result.json` in its working folder, so a large
result never has to fit in one message.
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

RESULT_FILE: Final = "result.json"

type JobFailureKind = Literal["network", "auth", "plugin", "program"]
"""Why a Job failed: the site's network, its login, a plugin, or the Job's own program."""


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class JobStart(_Message):
    """Load `plugins` from `package`, then run `program` on `request` in `work_dir`."""

    type: Literal["job"] = "job"
    package: str
    plugins: tuple[str, ...]
    program: str
    request: JsonValue
    work_dir: str
    login: str | None = None
    """The path of a copy of a login in the working folder, for the program to pass on."""


class KeyOutcome(_Message):
    """How one plugin key's calls in a Job went, for the plugin's circuit breaker.

    `trailing_failures` counts the faults in a row at the end of the Job;
    `succeeded` says whether any call before them succeeded.
    """

    plugin: str
    key: str
    trailing_failures: int
    succeeded: bool
    last_failure: str = ""


class JobProgress(_Message):
    """How far the Job has got, and the process's peak memory in bytes."""

    type: Literal["progress"] = "progress"
    fraction: float | None = None
    message: str = ""
    peak_memory: int


class JobFinished(_Message):
    """The program finished; its result is in the working folder."""

    type: Literal["finished"] = "finished"
    outcomes: tuple[KeyOutcome, ...] = ()
    peak_memory: int


class JobFailed(_Message):
    """The program failed; `plugin` and `key` name the provider at fault, when known."""

    type: Literal["failed"] = "failed"
    kind: JobFailureKind
    message: str
    plugin: str | None = None
    key: str | None = None
    outcomes: tuple[KeyOutcome, ...] = ()
    peak_memory: int


type FromJob = Annotated[JobProgress | JobFinished | JobFailed, Field(discriminator="type")]

FROM_JOB: Final = TypeAdapter[FromJob](FromJob)
