from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class NormalizationStrategy(StrEnum):
    PASSTHROUGH = "passthrough"
    REMUX = "remux"
    TRANSCODE = "transcode"


@dataclass(frozen=True)
class MediaProbe:
    path: Path
    video_codec: str
    pixel_format: str | None
    audio_codecs: tuple[str, ...]
    duration_seconds: float | None
    width: int | None
    height: int | None
    video_profile: str | None = None
    video_level: int | None = None
    # ffprobe's comma-delimited format.format_name, normalized to lowercase.
    # An empty set means the container was not identified safely.
    container_formats: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NormalizedMedia:
    source_path: Path
    output_path: Path
    strategy: NormalizationStrategy
    original_probe: MediaProbe
    probe: MediaProbe
