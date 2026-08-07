"""Bounded source validation using the production ffprobe module."""

import hashlib
from pathlib import Path

from app.instagram.collector.contracts import ValidatedSource
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.media.probe import probe_media


class FfprobeSourceValidator:
    def __init__(self, workspace_root: Path, maximum_bytes: int) -> None:
        self._workspace_root = workspace_root.resolve(strict=False)
        self._maximum_bytes = maximum_bytes

    def validate(self, temporary_path: Path) -> ValidatedSource:
        path = temporary_path.resolve(strict=False)
        if self._workspace_root not in path.parents or not path.is_file():
            raise CollectorRuntimeError(RuntimeReasonCode.VALIDATION_FAILED)
        byte_size = path.stat().st_size
        if byte_size <= 0 or byte_size > self._maximum_bytes:
            raise CollectorRuntimeError(RuntimeReasonCode.VALIDATION_FAILED)
        try:
            probe = probe_media(path)
        except Exception as error:
            raise CollectorRuntimeError(RuntimeReasonCode.VALIDATION_FAILED) from error
        if (
            "mp4" not in probe.container_formats
            or not probe.audio_codecs
            or probe.duration_seconds is None
            or probe.duration_seconds <= 0
            or probe.width is None
            or probe.width <= 0
            or probe.height is None
            or probe.height <= 0
        ):
            raise CollectorRuntimeError(RuntimeReasonCode.VALIDATION_FAILED)
        return ValidatedSource(
            sha256=_sha256(path),
            byte_size=byte_size,
            content_type="video/mp4",
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
