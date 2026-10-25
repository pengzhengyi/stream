"""A plugin's progress reaches whoever listens around its call, and nobody otherwise."""

import math

from medleyplay.plugin_api import report_progress
from medleyplay.plugin_api.progress import MAX_MESSAGE, reporting_to


def test_a_report_inside_a_listened_call_reaches_the_listener() -> None:
    heard: list[tuple[float | None, str]] = []

    with reporting_to(lambda fraction, message: heard.append((fraction, message))):
        report_progress(0.25, "Downloading")
        report_progress()

    assert heard == [(0.25, "Downloading"), (None, "")]


def test_a_report_with_nobody_listening_does_nothing() -> None:
    report_progress(0.5, "Downloading")


def test_a_fraction_out_of_range_is_kept_in_range_and_nan_is_unknown() -> None:
    heard: list[float | None] = []

    with reporting_to(lambda fraction, _: heard.append(fraction)):
        report_progress(1.5)
        report_progress(-1)
        report_progress(math.nan)

    assert heard == [1.0, 0.0, None]


def test_a_long_message_is_cut_short() -> None:
    heard: list[str] = []

    with reporting_to(lambda _, message: heard.append(message)):
        report_progress(None, "x" * (MAX_MESSAGE + 50))

    assert heard == ["x" * MAX_MESSAGE]
