"""A Job's program, run in this process: its outcome, its result file, and its plugin calls."""

from pathlib import Path

from medleyplay.plugin_host.job import run_job
from medleyplay.plugin_host.job_wire import (
    RESULT_FILE,
    JobFailed,
    JobFinished,
    JobProgress,
    JobStart,
    KeyOutcome,
)
from tests.support.echo import Say
from tests.support.hosts import TEST_PLUGINS
from tests.support.programs import Echoed, EchoJob


def _run(
    tmp_path: Path, request: EchoJob, program: str = "tests.support.programs:ECHO"
) -> tuple[JobFinished | JobFailed, list[JobProgress]]:
    start = JobStart(
        package=TEST_PLUGINS,
        plugins=("parrot",),
        program=program,
        request=request.model_dump(mode="json"),
        work_dir=str(tmp_path),
    )
    progress: list[JobProgress] = []
    return run_job(start, progress.append), progress


def test_a_finished_program_writes_its_result_and_reports_each_keys_calls(tmp_path: Path) -> None:
    outcome, progress = _run(tmp_path, EchoJob(text="x", steps=2, say=Say(text="hi")))

    assert isinstance(outcome, JobFinished)
    assert outcome.outcomes == (
        KeyOutcome(plugin="parrot", key="parrot", trailing_failures=0, succeeded=True),
    )
    assert Echoed.model_validate_json((tmp_path / RESULT_FILE).read_text()) == Echoed(text="hi")
    assert [(p.fraction, p.message) for p in progress] == [(0.5, "Step 1"), (1.0, "Step 2")]


def test_progress_a_plugin_reports_during_a_call_is_the_jobs_progress(tmp_path: Path) -> None:
    _, progress = _run(tmp_path, EchoJob(text="x", steps=1, say=Say(text="hi", progress=0.3)))

    assert [(p.fraction, p.message) for p in progress] == [(1.0, "Step 1"), (0.3, "Saying")]


def test_a_plugin_fault_the_program_does_not_catch_fails_it_naming_the_provider(
    tmp_path: Path,
) -> None:
    outcome, _ = _run(tmp_path, EchoJob(text="x", say=Say(text="boom", raises="value")))

    assert isinstance(outcome, JobFailed)
    assert (outcome.kind, outcome.message, outcome.plugin, outcome.key) == (
        "plugin",
        "ValueError: boom",
        "parrot",
        "parrot",
    )
    assert outcome.outcomes[0].trailing_failures == 1


def test_a_caught_plugin_fault_is_still_reported_for_the_circuit_breaker(tmp_path: Path) -> None:
    request = EchoJob(text="x", say=Say(text="boom", raises="value"), catch_failure=True)

    outcome, _ = _run(tmp_path, request)

    assert isinstance(outcome, JobFinished)
    assert outcome.outcomes == (
        KeyOutcome(
            plugin="parrot",
            key="parrot",
            trailing_failures=1,
            succeeded=False,
            last_failure="ValueError: boom",
        ),
    )


def test_network_and_login_failures_keep_their_kind(tmp_path: Path) -> None:
    network, _ = _run(tmp_path, EchoJob(text="x", say=Say(text="down", raises="network")))
    login, _ = _run(tmp_path, EchoJob(text="x", say=Say(text="expired", raises="auth")))

    assert isinstance(network, JobFailed)
    assert isinstance(login, JobFailed)
    assert (network.kind, login.kind) == ("network", "auth")


def test_a_name_that_is_not_a_job_program_fails_as_the_programs_fault(tmp_path: Path) -> None:
    outcome, _ = _run(tmp_path, EchoJob(text="x"), program="tests.support.programs:echo_kind")

    assert isinstance(outcome, JobFailed)
    assert (outcome.kind, outcome.message) == (
        "program",
        "TypeError: tests.support.programs:echo_kind isn't a JobProgram.",
    )
