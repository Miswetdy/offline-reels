"""Small local MP4 normalizer, intentionally independent of the API package."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


class NormalizationError(RuntimeError):
    """The downloaded media could not be made into a playable MVP MP4."""


def normalize_to_mp4(source: Path, destination: Path, *, timeout_seconds: int = 600) -> None:
    """Transcode to H.264/AAC and atomically publish ``destination``."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file() or source.stat().st_size == 0:
        raise NormalizationError("NORMALIZATION_INPUT_INVALID")
    if destination.exists():
        raise NormalizationError("NORMALIZATION_DESTINATION_EXISTS")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".normalizing-", suffix=".mp4", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    command = [
        "ffmpeg", "-y", "-v", "error", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
        "-profile:v", "main", "-level:v", "4.1", "-pix_fmt", "yuv420p",
        "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(temporary),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            raise NormalizationError("NORMALIZATION_FAILED")
        _validate(temporary, timeout_seconds)
        os.replace(temporary, destination)
    except subprocess.TimeoutExpired as error:
        raise NormalizationError("NORMALIZATION_TIMEOUT") from error
    except OSError as error:
        raise NormalizationError("FFMPEG_UNAVAILABLE") from error
    finally:
        temporary.unlink(missing_ok=True)


def _validate(path: Path, timeout_seconds: int) -> None:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0", "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise NormalizationError("NORMALIZATION_VALIDATION_FAILED")
