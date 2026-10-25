"""The Library models: what a location may say."""

import pytest
from pydantic import ValidationError

from medleyplay.plugin_api import FileLocation


@pytest.mark.parametrize(("offset", "length"), [(-1, 4), (0, -4)])
def test_a_location_with_a_negative_slice_is_refused(offset: int, length: int) -> None:
    with pytest.raises(ValidationError):
        FileLocation(local_path="/music/Old.zip", offset=offset, length=length)
