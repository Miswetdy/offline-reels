from pathlib import Path

import pytest

from app.media.compatibility import is_canonical_media, select_normalization_strategy
from app.media.errors import MediaCompatibilityError
from app.media.models import MediaProbe, NormalizationStrategy


def make_probe(
    *,
    video_codec: str = "h264",
    pixel_format: str | None = "yuv420p",
    audio_codecs: tuple[str, ...] = (),
    duration_seconds: float | None = 1.0,
    width: int | None = 720,
    height: int | None = 1280,
) -> MediaProbe:
    return MediaProbe(
        path=Path("input.mp4"),
        video_codec=video_codec,
        pixel_format=pixel_format,
        audio_codecs=audio_codecs,
        duration_seconds=duration_seconds,
        width=width,
        height=height,
    )


@pytest.mark.parametrize("audio_codecs", [(), ("aac",)])
def test_canonical_h264_yuv420p_media_is_remuxed(audio_codecs: tuple[str, ...]) -> None:
    strategy = select_normalization_strategy(make_probe(audio_codecs=audio_codecs))
    assert strategy is NormalizationStrategy.REMUX


@pytest.mark.parametrize(
    "probe",
    [
        make_probe(video_codec="vp9"),
        make_probe(video_codec="av1"),
        make_probe(pixel_format="yuv444p"),
        make_probe(audio_codecs=("opus",)),
        make_probe(audio_codecs=("",)),
    ],
)
def test_incompatible_media_is_transcoded(probe: MediaProbe) -> None:
    assert select_normalization_strategy(probe) is NormalizationStrategy.TRANSCODE


@pytest.mark.parametrize(
    "probe",
    [
        make_probe(video_codec=""),
        make_probe(duration_seconds=0),
        make_probe(width=0),
        make_probe(height=None),
    ],
)
def test_invalid_primary_video_metadata_is_rejected(probe: MediaProbe) -> None:
    with pytest.raises(MediaCompatibilityError):
        select_normalization_strategy(probe)
    assert not is_canonical_media(probe)
