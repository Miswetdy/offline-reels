from app.media.errors import MediaCompatibilityError
from app.media.models import MediaProbe, NormalizationStrategy

CANONICAL_VIDEO_CODEC = "h264"
CANONICAL_PIXEL_FORMAT = "yuv420p"
CANONICAL_AUDIO_CODEC = "aac"


def select_normalization_strategy(probe: MediaProbe) -> NormalizationStrategy:
    """Choose the least destructive way to produce the MVP-compatible MP4."""

    _validate_required_video_metadata(probe)
    if (
        probe.video_codec.lower() == CANONICAL_VIDEO_CODEC
        and probe.pixel_format == CANONICAL_PIXEL_FORMAT
        and all(codec.lower() == CANONICAL_AUDIO_CODEC for codec in probe.audio_codecs)
    ):
        return NormalizationStrategy.REMUX
    return NormalizationStrategy.TRANSCODE


def is_canonical_media(probe: MediaProbe) -> bool:
    try:
        return select_normalization_strategy(probe) is NormalizationStrategy.REMUX
    except MediaCompatibilityError:
        return False


def _validate_required_video_metadata(probe: MediaProbe) -> None:
    if not probe.video_codec:
        raise MediaCompatibilityError("Media has no video stream.")
    if probe.duration_seconds is None or probe.duration_seconds <= 0:
        raise MediaCompatibilityError("Media duration must be greater than zero.")
    if probe.width is None or probe.width <= 0 or probe.height is None or probe.height <= 0:
        raise MediaCompatibilityError("Media dimensions must be greater than zero.")
