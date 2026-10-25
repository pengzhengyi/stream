"""Reporting how far a long call has got, such as a download as its bytes arrive.

Inside a Job, the report becomes the Job's progress, which also keeps the Job
from being killed as idle; anywhere else it does nothing:

```python
def download(self, request: DownloadPart) -> Downloaded:
    for done, total in chunks():
        report_progress(done / total, "Downloading")
```
"""

import contextlib
import math
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from typing import Final

type ProgressSink = Callable[[float | None, str], None]

MAX_MESSAGE: Final = 200
_sink: ContextVar[ProgressSink | None] = ContextVar("progress_sink", default=None)


def report_progress(fraction: float | None = None, message: str = "") -> None:
    """Report how far the call has got: a fraction from 0 to 1 when known, and what it's doing."""
    sink = _sink.get()
    if sink is None:
        return
    if fraction is not None:
        fraction = None if math.isnan(fraction) else min(max(fraction, 0.0), 1.0)
    sink(fraction, message[:MAX_MESSAGE])


@contextlib.contextmanager
def reporting_to(sink: ProgressSink) -> Iterator[None]:
    """Send the reports made inside the block to `sink`; the core uses this around a call."""
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)
