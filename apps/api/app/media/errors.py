class MediaNormalizationError(RuntimeError):
    """Base error for a media normalization operation."""


class MediaProbeError(MediaNormalizationError):
    """ffprobe could not return a usable media description."""


class MediaProbeTimeoutError(MediaProbeError):
    """ffprobe exceeded its allowed execution time."""


class MediaDecodeError(MediaNormalizationError):
    """ffmpeg could not fully decode a media file."""


class MediaDecodeTimeoutError(MediaDecodeError):
    """Decode validation exceeded its allowed execution time."""


class MediaCompatibilityError(MediaNormalizationError):
    """The input or normalized output has no valid primary video stream."""


class MediaNormalizationCommandError(MediaNormalizationError):
    """ffmpeg could not create a normalized output."""


class MediaNormalizationTimeoutError(MediaNormalizationCommandError):
    """The normalization command exceeded its allowed execution time."""
