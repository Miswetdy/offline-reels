"""Explicit composition for a future operator runner; importing is inert."""

from dataclasses import dataclass
from pathlib import Path

from app.instagram.collector.runtime.minio_storage import (
    MinioClientPort,
    MinioCollectorSourceStorage,
)
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings
from app.instagram.collector.runtime.validator import FfprobeSourceValidator


@dataclass(frozen=True)
class CollectorRuntimeAdapters:
    validator: FfprobeSourceValidator
    source_storage: MinioCollectorSourceStorage


def build_runtime_adapters(
    settings: CollectorRuntimeSettings,
    *,
    repository_root: Path,
    minio_client: MinioClientPort,
    minio_bucket: str,
) -> CollectorRuntimeAdapters:
    settings.require_live(repository_root=repository_root)
    assert settings.workspace_root is not None
    return CollectorRuntimeAdapters(
        validator=FfprobeSourceValidator(settings.workspace_root, settings.maximum_reel_bytes),
        source_storage=MinioCollectorSourceStorage(
            minio_client,
            minio_bucket,
            settings.workspace_root,
            settings.maximum_reel_bytes,
        ),
    )
