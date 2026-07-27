from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class NormalizationStrategy(StrEnum):
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


@dataclass(frozen=True)
class NormalizedMedia:
    source_path: Path
    output_path: Path
    strategy: NormalizationStrategy
    original_probe: MediaProbe
    probe: MediaProbe
