import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.media.compatibility import is_canonical_media, select_normalization_strategy
from app.media.errors import (
    MediaCompatibilityError,
    MediaDecodeError,
    MediaDecodeTimeoutError,
    MediaNormalizationCommandError,
    MediaNormalizationTimeoutError,
)
from app.media.models import NormalizationStrategy, NormalizedMedia
from app.media.probe import probe_media

DEFAULT_FFMPEG_TIMEOUT_SECONDS = 10 * 60


def validate_decode(path: Path, *, timeout_seconds: int = DEFAULT_FFMPEG_TIMEOUT_SECONDS) -> None:
    """Require ffmpeg to decode all streams without an error."""

    command = ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0", "-f", "null", "-"]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise MediaDecodeTimeoutError("ffmpeg decode validation timed out.") from error
    except OSError as error:
        raise MediaDecodeError("ffmpeg could not be started for decode validation.") from error
    if completed.returncode != 0:
        raise MediaDecodeError("ffmpeg could not decode the media file.")


@contextmanager
def normalize_video(
    input_path: Path,
    *,
    probe_timeout_seconds: int = 30,
    ffmpeg_timeout_seconds: int = DEFAULT_FFMPEG_TIMEOUT_SECONDS,

) -> Iterator[NormalizedMedia]:
    """Yield a verified canonical MP4 and deterministically remove it on exit.

    The caller must finish every read or upload of ``result.output_path`` inside
    the context. The output is removed on both normal and exceptional exit.
    """

    with tempfile.TemporaryDirectory(prefix="offline-reels-normalized-") as directory:
        yield _normalize_to_output(
            input_path,
            Path(directory) / "normalized.mp4",
            probe_timeout_seconds=probe_timeout_seconds,
            ffmpeg_timeout_seconds=ffmpeg_timeout_seconds,
        )


def _normalize_to_output(
    input_path: Path,
    output_path: Path,
    *,
    probe_timeout_seconds: int,
    ffmpeg_timeout_seconds: int,
) -> NormalizedMedia:
    """Normalize input into a verified canonical MP4 at a private temp path.

    The requested output is not touched until temporary output passes probe,
    decode, compatibility, and non-empty-size validation.
    """

    source = input_path.resolve()
    destination = output_path.resolve()
    if not source.is_file():
        raise MediaNormalizationCommandError("Input media file does not exist.")
    if source == destination:
        raise MediaNormalizationCommandError("Input and output paths must differ.")
    if destination.exists():
        raise MediaNormalizationCommandError("Output media file already exists.")
    if destination.suffix.lower() != ".mp4":
        raise MediaNormalizationCommandError("Normalized output must use the .mp4 extension.")
    if not destination.parent.is_dir():
        raise MediaNormalizationCommandError("Output directory does not exist.")

    source_probe = probe_media(source, timeout_seconds=probe_timeout_seconds)
    validate_decode(source, timeout_seconds=ffmpeg_timeout_seconds)
    strategy = select_normalization_strategy(source_probe)
    temporary_path = _create_temporary_output(destination.parent)
    try:
        _run_normalization(
            source,
            temporary_path,
            strategy,
            timeout_seconds=ffmpeg_timeout_seconds,
        )
        normalized_probe = probe_media(temporary_path, timeout_seconds=probe_timeout_seconds)
        validate_decode(temporary_path, timeout_seconds=ffmpeg_timeout_seconds)
        if not is_canonical_media(normalized_probe):
            raise MediaCompatibilityError("Normalized output is not MVP-compatible media.")
        if temporary_path.stat().st_size <= 0:
            raise MediaNormalizationCommandError("Normalized output is empty.")
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    return NormalizedMedia(
        source_path=source,
        output_path=destination,
        strategy=strategy,
        original_probe=source_probe,
        probe=normalized_probe,
    )


def _create_temporary_output(directory: Path) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".offline-reels-normalizing-",
        suffix=".mp4",
        dir=directory,
    )
    os.close(descriptor)
    return Path(temporary_name)


def _run_normalization(
    source: Path,
    temporary_output: Path,
    strategy: NormalizationStrategy,
    *,
    timeout_seconds: int,
) -> None:
    command = _remux_command(source, temporary_output)
    if strategy is NormalizationStrategy.TRANSCODE:
        command = _transcode_command(source, temporary_output)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise MediaNormalizationTimeoutError("ffmpeg normalization timed out.") from error
    except OSError as error:
        raise MediaNormalizationCommandError(
            "ffmpeg could not be started for normalization."
        ) from error
    if completed.returncode != 0:
        raise MediaNormalizationCommandError("ffmpeg could not normalize the media file.")


def _remux_command(source: Path, output: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]


def _transcode_command(source: Path, output: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-level:v",
        "4.1",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output),
    ]
