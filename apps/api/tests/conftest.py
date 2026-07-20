import os

# This value is test-only and never used by a running development or production API.
os.environ.setdefault(
    "VIDEO_CURSOR_SECRET", "test-only-video-cursor-secret-with-at-least-32-characters"
)
