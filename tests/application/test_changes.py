"""Change notices: every listener hears each change a service tells, in order."""

from medleyplay.application.changes import Changes


def test_every_listener_hears_each_change_told_after_it_listened() -> None:
    changes = Changes()
    first: list[str] = []
    second: list[str] = []
    changes.tell("unheard")
    changes.listen(first.append)
    changes.listen(second.append)

    changes.tell("catalog")
    changes.tell("settings")

    assert first == second == ["catalog", "settings"]
