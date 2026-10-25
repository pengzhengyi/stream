"""The bilibili plugin registers a resolver, a downloader, and a login check for `bilibili`."""

from medleyplay.plugin_host.loader import BUILT_IN_PLUGINS, load_plugins


def test_the_plugin_answers_every_source_operation_for_bilibili() -> None:
    endpoints = load_plugins(BUILT_IN_PLUGINS, ["bilibili"], lambda _: None)

    assert sorted(endpoints) == [
        ("credential_spec", "bilibili", "check"),
        ("source_downloader", "bilibili", "download"),
        ("source_resolver", "bilibili", "canonicalize"),
        ("source_resolver", "bilibili", "read"),
    ]
