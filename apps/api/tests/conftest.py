import os
from importlib.util import find_spec

import pytest

# This value is test-only and never used by a running development or production API.
os.environ.setdefault(
    "VIDEO_CURSOR_SECRET", "test-only-video-cursor-secret-with-at-least-32-characters"
)


def pytest_collection_modifyitems(config, items) -> None:
    """Keep the ordinary API suite independent of the optional Collector extra."""

    del config
    if find_spec("yt_dlp") is not None:
        return
    skip = pytest.mark.skip(reason="requires the optional Collector extra")
    for item in items:
        if item.path.name.startswith("test_instagram_collector"):
            item.add_marker(skip)
