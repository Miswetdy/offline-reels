import json
import math
import subprocess
from pathlib import Path
from typing import Any

from app.media.errors import MediaProbeError, MediaProbeTimeoutError
from app.media.models import MediaProbe

DEFAULT_PROBE_TIMEOUT_SECONDS = 30


def probe_media(path: Path, *, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS) -> MediaProbe:
    """Read the primary video and audio stream metadata through ffprobe."""

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise MediaProbeTimeoutError("ffprobe timed out.") from error
    except OSError as error:
        raise MediaProbeError("ffprobe could not be started.") from error

    if completed.returncode != 0:
        raise MediaProbeError("ffprobe could not inspect the media file.")
    return _parse_probe_output(path, completed.stdout)


def _parse_probe_output(path: Path, output: str) -> MediaProbe:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise MediaProbeError("ffprobe returned malformed JSON.") from error
    if not isinstance(payload, dict):
        raise MediaProbeError("ffprobe returned an invalid document.")

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise MediaProbeError("ffprobe did not return streams.")

    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video_stream is None:
        raise MediaProbeError("Media has no video stream.")

    video_codec = _required_string(video_stream, "codec_name")
    pixel_format = _optional_string(video_stream, "pix_fmt")
    audio_codecs = tuple(
        _optional_string(stream, "codec_name") or ""
        for stream in streams
        if isinstance(stream, dict)
        and stream.get("codec_type") == "audio"
    )

    format_info = payload.get("format")
    duration = None
    container_formats: frozenset[str] = frozenset()
    if isinstance(format_info, dict):
        duration = _optional_duration(format_info.get("duration"))
        container_formats = _container_formats(format_info.get("format_name"))

    return MediaProbe(
        path=path,
        video_codec=video_codec,
        pixel_format=pixel_format,
        audio_codecs=audio_codecs,
        duration_seconds=duration,
        width=_optional_positive_integer(video_stream.get("width")),
        height=_optional_positive_integer(video_stream.get("height")),
        video_profile=_optional_string(video_stream, "profile"),
        video_level=_optional_nonnegative_integer(video_stream.get("level")),
        container_formats=container_formats,
    )


def _required_string(value: dict[str, Any], key: str) -> str:
    result = _optional_string(value, key)
    if result is None:
        raise MediaProbeError(f"ffprobe did not return {key} for the video stream.")
    return result


def _optional_string(value: dict[str, Any], key: str) -> str | None:
    result = value.get(key)
    return result if isinstance(result, str) and result else None


def _optional_duration(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        duration = float(value)
    except ValueError:
        return None
    return duration if math.isfinite(duration) else None


def _container_formats(value: object) -> frozenset[str]:
    """Parse ffprobe's format aliases without treating a file suffix as evidence."""

    if not isinstance(value, str):
        return frozenset()
    return frozenset(part.strip().lower() for part in value.split(",") if part.strip())


def _optional_positive_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _optional_nonnegative_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None
