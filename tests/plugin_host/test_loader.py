"""Finding plugins without importing them, and answering calls inside a host."""

import sys

import pytest

from medleyplay.plugin_host.host import answer
from medleyplay.plugin_host.loader import load_plugins, plugin_names
from medleyplay.plugin_host.wire import Call, Loaded, Loading, Quarantined
from tests.support.hosts import TEST_PLUGINS


def test_plugin_names_come_from_module_names_with_hyphens() -> None:
    names = plugin_names(TEST_PLUGINS)

    assert {"parrot", "broken-import", "hangs-on-import"} <= set(names)
    assert list(names) == sorted(names)


def test_finding_plugin_names_imports_none_of_them() -> None:
    plugin_names(TEST_PLUGINS)

    assert "tests.support.plugins.broken_import" not in sys.modules


def test_a_module_that_is_not_a_package_has_no_plugins() -> None:
    with pytest.raises(ValueError, match="isn't a package of plugins"):
        plugin_names("tests.support.echo")


def test_loading_reports_each_plugin_before_and_after_its_import() -> None:
    heard: list[Loading | Loaded | Quarantined] = []

    load_plugins(TEST_PLUGINS, ["parrot", "broken-import"], heard.append)

    assert heard == [
        Loading(name="broken-import"),
        Quarantined(name="broken-import", reason="RuntimeError: This plugin can't be imported."),
        Loading(name="parrot"),
        Loaded(name="parrot", keys={"echo": ("parrot",)}),
    ]


def test_a_request_that_does_not_match_the_operations_model_is_refused() -> None:
    endpoints = load_plugins(TEST_PLUGINS, ["parrot"], lambda _: None)
    call = Call(id=1, point="echo", key="parrot", operation="say", request={"words": "hi"})

    reply = answer(call, endpoints)

    assert reply.failure is not None
    assert reply.failure.kind == "request"
    assert reply.failure.message.startswith("The request is invalid:")


def test_a_reply_carries_the_calls_id_and_the_hosts_peak_memory() -> None:
    endpoints = load_plugins(TEST_PLUGINS, ["parrot"], lambda _: None)
    call = Call(id=7, point="echo", key="parrot", operation="say", request={"text": "hi"})

    reply = answer(call, endpoints)

    assert (reply.id, reply.reply, reply.failure) == (7, {"text": "hi", "calls": 0}, None)
    assert reply.peak_memory > 0
