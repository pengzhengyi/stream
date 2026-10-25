"""The plugin service: each plugin's state, calls through a real host, and faults."""

import sys

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.plugins import FAULT_AFTER, Lineup, PluginService
from medleyplay.domain.errors import (
    ForbiddenError,
    NotFoundError,
    PluginCallError,
    PluginUnavailableError,
)
from medleyplay.domain.plugins import PluginState, PluginStatus
from medleyplay.plugin_api import Operation
from medleyplay.plugin_host.client import (
    CallFailedError,
    HostBusyError,
    HostCommand,
    LoadReport,
    PluginHost,
)
from medleyplay.plugin_host.job_wire import KeyOutcome
from tests.support.echo import SAY, Said, Say
from tests.support.factories import AccountFactory
from tests.support.fakes import FakeClock
from tests.support.hosts import TEST_PLUGINS, started_plugins

ADMIN = AccountFactory.admin()

FAILING = Say(text="boom", raises="value")


def _status(plugins: PluginService, name: str) -> PluginStatus:
    return next(status for status in plugins.statuses(ADMIN) if status.name == name)


def _fail(plugins: PluginService, key: str, times: int) -> None:
    for _ in range(times):
        with pytest.raises(PluginCallError):
            plugins.call(SAY, key, FAILING)


def test_a_loaded_plugin_is_on_with_its_keys(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "mynah") as plugins:
        status = _status(plugins, "mynah")

    assert status == PluginStatus("mynah", PluginState.ON, keys={"echo": ("mynah", "myna")})


def test_each_plugin_that_is_not_on_says_why(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "parrot", "broken-import", unknown=("radio",)) as plugins:
        statuses = {status.name: status for status in plugins.statuses(ADMIN)}

    assert statuses["mynah"] == PluginStatus(
        "mynah", PluginState.OFF, "The config file turns it off."
    )
    assert statuses["broken-import"] == PluginStatus(
        "broken-import", PluginState.QUARANTINED, "RuntimeError: This plugin can't be imported."
    )
    assert statuses["radio"] == PluginStatus(
        "radio", PluginState.UNKNOWN, "The config file names no such plugin."
    )


def test_safe_mode_turns_every_plugin_off(units: sessionmaker[Session], clock: FakeClock) -> None:
    with started_plugins(units, clock, "parrot", safe_mode=True) as plugins:
        status = _status(plugins, "parrot")
        keys = plugins.available_keys()

    assert status == PluginStatus("parrot", PluginState.OFF, "Safe mode is on.")
    assert keys == {}


def test_only_an_admin_sees_the_plugins(units: sessionmaker[Session], clock: FakeClock) -> None:
    with started_plugins(units, clock) as plugins, pytest.raises(ForbiddenError):
        plugins.statuses(AccountFactory.member())


def test_a_call_goes_to_the_plugin_holding_the_key(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "parrot", "mynah") as plugins:
        said = plugins.call(SAY, "myna", Say(text="hello"))
        keys = plugins.available_keys()

    assert said == Said(text="hello")
    assert keys == {"echo": ["myna", "mynah", "parrot"]}


def test_a_key_no_plugin_that_is_on_holds_is_unavailable(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with (
        started_plugins(units, clock, "parrot") as plugins,
        pytest.raises(PluginUnavailableError, match="No plugin that is on answers echo for"),
    ):
        plugins.call(SAY, "mynah", Say(text="hello"))


@pytest.mark.parametrize("kind", ["network", "auth"])
def test_network_and_login_failures_never_fault_a_plugin(
    units: sessionmaker[Session], clock: FakeClock, kind: str
) -> None:
    request = Say.model_validate({"text": "down", "raises": kind})
    with started_plugins(units, clock, "parrot") as plugins:
        for _ in range(FAULT_AFTER + 1):
            with pytest.raises(PluginCallError) as failure:
                plugins.call(SAY, "parrot", request)
        status = _status(plugins, "parrot")

    assert (failure.value.kind, str(failure.value)) == (kind, "parrot: down")
    assert status.state is PluginState.ON


def test_five_plugin_failures_in_a_row_fault_the_plugin(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "parrot") as plugins:
        _fail(plugins, "parrot", FAULT_AFTER)
        status = _status(plugins, "parrot")
        keys = plugins.available_keys()
        with pytest.raises(PluginUnavailableError):
            plugins.call(SAY, "parrot", Say(text="hello"))

    assert status == PluginStatus(
        "parrot", PluginState.FAULTED, "ValueError: boom", {"echo": ("parrot",)}
    )
    assert keys == {}


def test_a_success_resets_the_count(units: sessionmaker[Session], clock: FakeClock) -> None:
    with started_plugins(units, clock, "parrot") as plugins:
        _fail(plugins, "parrot", FAULT_AFTER - 1)
        plugins.call(SAY, "parrot", Say(text="fine"))
        _fail(plugins, "parrot", FAULT_AFTER - 1)
        status = _status(plugins, "parrot")

    assert status.state is PluginState.ON


def test_a_working_key_cannot_hide_a_broken_one(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "mynah") as plugins:
        for _ in range(FAULT_AFTER):
            plugins.call(SAY, "myna", Say(text="fine"))
            with pytest.raises(PluginCallError):
                plugins.call(SAY, "mynah", FAILING)
        status = _status(plugins, "mynah")

    assert status.state is PluginState.FAULTED


def test_a_fault_survives_a_restart_until_an_admin_resets_it(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "parrot") as plugins:
        _fail(plugins, "parrot", FAULT_AFTER)

    with started_plugins(units, clock, "parrot") as restarted:
        after_restart = _status(restarted, "parrot").state
        reset = restarted.reset(ADMIN, "parrot")
        said = restarted.call(SAY, "parrot", Say(text="back"))

    with started_plugins(units, clock, "parrot") as restarted_again:
        after_reset = _status(restarted_again, "parrot").state

    assert after_restart is PluginState.FAULTED
    assert reset.state is PluginState.ON
    assert said.text == "back"
    assert after_reset is PluginState.ON


def test_resetting_a_plugin_that_is_not_faulted_changes_nothing(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "parrot") as plugins:
        status = plugins.reset(ADMIN, "parrot")

    assert status.state is PluginState.ON


def test_resetting_starts_the_count_again(units: sessionmaker[Session], clock: FakeClock) -> None:
    with started_plugins(units, clock, "parrot") as plugins:
        _fail(plugins, "parrot", FAULT_AFTER - 1)
        plugins.reset(ADMIN, "parrot")
        _fail(plugins, "parrot", 1)
        status = _status(plugins, "parrot")

    assert status.state is PluginState.ON


def test_resetting_a_plugin_that_does_not_exist_is_refused(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock) as plugins, pytest.raises(NotFoundError):
        plugins.reset(ADMIN, "bilibili")


def test_only_an_admin_resets_a_plugin(units: sessionmaker[Session], clock: FakeClock) -> None:
    with started_plugins(units, clock) as plugins, pytest.raises(ForbiddenError):
        plugins.reset(AccountFactory.member(), "parrot")


class _FailingHost:
    """A host holding `parrot` whose every call raises `error`."""

    report = LoadReport(loaded={"parrot": {"echo": ("parrot",)}})

    def __init__(self, error: Exception) -> None:
        self._error = error

    def start(self) -> LoadReport:
        return self.report

    def call[P, I: BaseModel, O: BaseModel](
        self, operation: Operation[P, I, O], key: str, request: I
    ) -> O:
        raise self._error

    def close(self) -> None:
        pass


def test_a_request_the_host_refuses_is_a_fault_in_the_core_not_the_plugin(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    refusing = _FailingHost(CallFailedError(kind="request", message="The request is invalid."))
    plugins = PluginService(units, clock, Lineup(("parrot",), ("parrot",)), refusing)
    plugins.start()

    with pytest.raises(RuntimeError, match="The plugin host refused a request"):
        plugins.call(SAY, "parrot", Say(text="hello"))
    assert _status(plugins, "parrot").state is PluginState.ON


def test_when_the_host_cannot_start_its_plugins_are_quarantined_and_unavailable(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    broken = PluginHost(
        ["parrot"], package=TEST_PLUGINS, command=HostCommand(argv=(sys.executable, "-c", "pass"))
    )
    plugins = PluginService(units, clock, Lineup(("parrot",), ("parrot",)), broken)
    plugins.start()

    status = _status(plugins, "parrot")
    with pytest.raises(PluginUnavailableError, match="The plugin host failed to start"):
        plugins.call(SAY, "parrot", Say(text="hello"))
    assert status == PluginStatus(
        "parrot", PluginState.QUARANTINED, "The plugin host failed to start."
    )


def test_a_busy_host_makes_the_call_unavailable(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    busy = _FailingHost(HostBusyError("The plugin host was busy for 2 s."))
    plugins = PluginService(units, clock, Lineup(("parrot",), ("parrot",)), busy)
    plugins.start()

    with pytest.raises(PluginUnavailableError, match="busy for 2 s"):
        plugins.call(SAY, "parrot", Say(text="hello"))


def _outcome(trailing: int, *, succeeded: bool = False) -> KeyOutcome:
    return KeyOutcome(
        plugin="parrot",
        key="parrot",
        trailing_failures=trailing,
        succeeded=succeeded,
        last_failure="ValueError: boom" if trailing else "",
    )


def test_a_jobs_faults_count_toward_faulting_like_the_hosts(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "parrot") as plugins:
        _fail(plugins, "parrot", FAULT_AFTER - 2)
        plugins.record_outcomes([_outcome(2)])
        status = _status(plugins, "parrot")

    assert status.state is PluginState.FAULTED


def test_a_job_whose_key_succeeded_before_failing_restarts_the_count(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "parrot") as plugins:
        _fail(plugins, "parrot", FAULT_AFTER - 1)
        plugins.record_outcomes([_outcome(1, succeeded=True)])
        _fail(plugins, "parrot", FAULT_AFTER - 2)
        status = _status(plugins, "parrot")

    assert status.state is PluginState.ON


def test_a_job_process_loads_only_the_plugins_for_its_points(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    with started_plugins(units, clock, "parrot", "mynah") as plugins:
        _fail(plugins, "mynah", FAULT_AFTER)
        for_echo = plugins.plugins_for(["echo"])
        for_nothing = plugins.plugins_for(["tag_reader"])

    assert for_echo == ("parrot",)
    assert for_nothing == ()
