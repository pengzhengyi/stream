"""The type of a row id taken from a request."""

from typing import Annotated

from pydantic import Field

RowId = Annotated[int, Field(ge=1, le=2**63 - 1)]
"""An id of a row in the database: positive, and no larger than SQLite's 64-bit INTEGER holds."""
