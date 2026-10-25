"""A real plugin host, driven through the client: loading, calls, and every way they fail."""

import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from medleyplay.plugin_host.client import (
    CallFailedError,
    HostBusyError,
    HostCommand,
    HostStartError,
    PluginHost,
)
from tests.support.echo import SAY, SAY_QUICKLY, Said, Say
from tests.support.hosts import TEST_PLUGINS, started_host


def test_the_host_reports_each_loaded_plugins_keys() -> None:
    with started_host("parrot", "mynah") as host:
        report = host.report

    assert report.loaded == {"mynah": {"echo": ("mynah", "myna")}, "parrot": {"echo": ("parrot",)}}
    assert report.quarantined == {}
    assert report.owner("echo", "myna") == "mynah"
    assert report.owner("echo", "crow") is None


def test_a_call_returns_the_providers_reply() -> None:
    with started_host("parrot") as host:
        said = host.call(SAY, "parrot", Say(text="hello"))

    assert said == Said(text="hello")


def test_a_plugin_that_prints_cannot_corrupt_the_protocol() -> None:
    with started_host("mynah") as host:
        said = host.call(SAY, "mynah", Say(text="hello", print_text=True))

    assert said == Said(text="hello")


@pytest.mark.parametrize(
    ("plugin", "reason"),
    [
        ("broken-import", "RuntimeError: This plugin can't be imported."),
        ("future-version", "ValueError: Written for plugin API 99; this server has 1."),
        ("not-a-plugin", "TypeError: The module defines no `plugin = Plugin(...)`."),
        ("hangs-on-import", "It hung or crashed the plugin host while loading."),
        ("crashes-on-import", "It hung or crashed the plugin host while loading."),
        (
            "no-such-plugin",
            "ModuleNotFoundError: No module named 'tests.support.plugins.no_such_plugin'",
        ),
    ],
)
def test_a_plugin_that_fails_to_load_is_quarantined_and_the_rest_load(
    plugin: str, reason: str
) -> None:
    with started_host(plugin, "parrot") as host:
        report = host.report
        said = host.call(SAY, "parrot", Say(text="still here"))

    assert report.quarantined == {plugin: reason}
    assert list(report.loaded) == ["parrot"]
    assert said.text == "still here"


def test_a_plugin_claiming_a_taken_key_is_quarantined_as_a_whole() -> None:
    with started_host("parrot", "squatter") as host:
        report = host.report

    assert report.loaded == {"parrot": {"echo": ("parrot",)}}
    assert report.quarantined == {
        "squatter": "ValueError: echo key 'parrot' is already taken by parrot."
    }


@pytest.mark.parametrize(
    ("raises", "kind", "message"),
    [
        ("network", "network", "boom"),
        ("auth", "auth", "boom"),
        ("value", "plugin", "ValueError: boom"),
        ("exit", "plugin", "SystemExit: boom"),
    ],
)
def test_a_providers_exception_fails_the_call_with_its_kind(
    raises: str, kind: str, message: str
) -> None:
    with started_host("parrot") as host:
        with pytest.raises(CallFailedError) as failure:
            host.call(SAY, "parrot", Say.model_validate({"text": "boom", "raises": raises}))
        still_answering = host.call(SAY, "parrot", Say(text="after"))

    assert (failure.value.kind, str(failure.value)) == (kind, message)
    assert still_answering.text == "after"


def test_a_reply_of_the_wrong_type_is_a_plugin_failure() -> None:
    with started_host("parrot") as host, pytest.raises(CallFailedError) as failure:
        host.call(SAY, "parrot", Say(text="hello", wrong_reply=True))

    assert failure.value.kind == "plugin"
    assert str(failure.value) == "TypeError: echo.say returned Say, not Said."


def test_a_key_no_plugin_holds_is_refused_as_a_request_failure() -> None:
    with started_host("parrot") as host, pytest.raises(CallFailedError) as failure:
        host.call(SAY, "crow", Say(text="hello"))

    assert failure.value.kind == "request"
    assert str(failure.value) == "No provider answers echo.say for 'crow'."


def test_a_missed_deadline_fails_the_call_and_the_next_call_gets_a_new_host() -> None:
    with started_host("parrot") as host:
        host.call(SAY, "parrot", Say(text="first", count_calls=True))
        with pytest.raises(CallFailedError) as failure:
            host.call(SAY, "parrot", Say(text="slow", sleep_seconds=10))
        after = host.call(SAY, "parrot", Say(text="after", count_calls=True))

    assert failure.value.kind == "plugin"
    assert str(failure.value) == "echo.say missed its deadline of 2 s."
    assert after.calls == 1


def test_a_host_crashing_during_a_call_fails_it_and_the_next_call_gets_a_new_host() -> None:
    with started_host("parrot") as host:
        with pytest.raises(CallFailedError) as failure:
            host.call(SAY, "parrot", Say(text="crash", crash=True))
        after = host.call(SAY, "parrot", Say(text="after"))

    assert failure.value.kind == "plugin"
    assert str(failure.value) == "The plugin host exited during echo.say."
    assert after.text == "after"


def test_a_host_that_died_between_calls_is_replaced_without_failing_the_next_call() -> None:
    with started_host("parrot") as host:
        host.call(SAY, "parrot", Say(text="first", exit_after_seconds=0.1))
        time.sleep(0.5)
        after = host.call(SAY, "parrot", Say(text="after", count_calls=True))

    assert after == Said(text="after", calls=1)


def test_a_host_past_its_memory_limit_is_replaced_before_the_next_call() -> None:
    with started_host("parrot", memory_limit=1) as host:
        host.call(SAY, "parrot", Say(text="first", count_calls=True))
        second = host.call(SAY, "parrot", Say(text="second", count_calls=True))

    assert second.calls == 1


def test_a_host_within_its_memory_limit_keeps_answering() -> None:
    with started_host("parrot") as host:
        host.call(SAY, "parrot", Say(text="first", count_calls=True))
        second = host.call(SAY, "parrot", Say(text="second", count_calls=True))

    assert second.calls == 2


def test_a_call_waiting_past_its_deadline_for_a_busy_host_is_refused() -> None:
    with started_host("parrot") as host:
        slow = threading.Thread(
            target=host.call, args=(SAY, "parrot", Say(text="slow", sleep_seconds=1.5))
        )
        slow.start()
        time.sleep(0.2)
        with pytest.raises(HostBusyError) as busy:
            host.call(SAY_QUICKLY, "parrot", Say(text="quick"))
        slow.join()

    assert str(busy.value) == "The plugin host was busy for 0.5 s."


def test_a_host_that_exits_before_loading_anything_fails_to_start() -> None:
    host = PluginHost(
        ["parrot"],
        package=TEST_PLUGINS,
        command=HostCommand(argv=(sys.executable, "-c", "pass")),
        load_deadline=timedelta(seconds=4),
    )

    with pytest.raises(HostStartError):
        host.start()


def test_a_closed_host_starts_again_on_the_next_call() -> None:
    with started_host("parrot") as host:
        host.close()
        said = host.call(SAY, "parrot", Say(text="again"))

    assert said.text == "again"


def _fake_host(mode: str) -> PluginHost:
    script = Path(__file__).resolve().parents[1] / "support" / "fake_host.py"
    return PluginHost(
        ["parrot"],
        package=TEST_PLUGINS,
        command=HostCommand(argv=(sys.executable, str(script), mode)),
        load_deadline=timedelta(seconds=4),
    )


def test_a_reply_the_client_cannot_validate_is_a_plugin_failure() -> None:
    host = _fake_host("invalid-reply")
    host.start()

    with pytest.raises(CallFailedError) as failure:
        host.call(SAY, "parrot", Say(text="hello"))
    host.close()

    assert failure.value.kind == "plugin"
    assert str(failure.value).startswith("The reply is invalid:")


def test_a_line_that_is_not_a_message_is_treated_as_the_host_dying() -> None:
    host = _fake_host("garbage")
    host.start()

    with pytest.raises(CallFailedError, match=r"The plugin host exited during echo\.say"):
        host.call(SAY, "parrot", Say(text="hello"))
    host.close()


def test_a_reply_to_another_call_is_skipped() -> None:
    host = _fake_host("stale-reply")
    host.start()

    said = host.call(SAY, "parrot", Say(text="hello"))
    host.close()

    assert said.text == "new"


def test_a_host_that_keeps_announcing_a_quarantined_plugin_fails_to_start() -> None:
    # The fake replies mid-load, which quarantines `parrot`; its next start announces
    # `parrot` again, though it was no longer asked to load it.
    host = _fake_host("reply-while-loading")

    with pytest.raises(HostStartError, match="announced 'parrot', which it wasn't asked to load"):
        host.start()
