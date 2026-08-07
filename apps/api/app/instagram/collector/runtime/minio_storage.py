"""Prefix-bound MinIO source storage for validated Collector sources."""

from pathlib import Path
from typing import Protocol

from app.instagram.collector.canonical import source_object_key
from app.instagram.collector.contracts import PublishedSource
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode


class MinioClientPort(Protocol):
    def stat_object(self, bucket_name: str, object_name: str): ...

    def fput_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        *,
        content_type: str,
    ): ...

    def remove_object(self, bucket_name: str, object_name: str): ...


class MinioCollectorSourceStorage:
    def __init__(
        self,
        client: MinioClientPort,
        bucket: str,
        workspace_root: Path,
        maximum_bytes: int,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._workspace_root = workspace_root.resolve(strict=False)
        self._temporary_root = self._workspace_root / "temporary"
        self._maximum_bytes = maximum_bytes

    def temporary_path(self, shortcode: str) -> Path:
        key = source_object_key(shortcode)
        return self._temporary_root / Path(key).name.replace(".mp4", ".part")

    def publish(self, temporary_path: Path, object_key: str) -> PublishedSource:
        key = self._validated_key(object_key)
        path = self._validated_temporary_path(temporary_path)
        if path.stat().st_size <= 0 or path.stat().st_size > self._maximum_bytes:
            raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_FAILED)
        if self.exists(key):
            return PublishedSource(object_key=key, created_by_attempt=False)
        try:
            self._client.fput_object(self._bucket, key, str(path), content_type="video/mp4")
        except Exception as error:
            raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_FAILED) from error
        return PublishedSource(object_key=key, created_by_attempt=True)

    def exists(self, object_key: str) -> bool:
        key = self._validated_key(object_key)
        try:
            self._client.stat_object(self._bucket, key)
        except Exception as error:
            if _is_not_found(error):
                return False
            raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_FAILED) from error
        return True

    def delete(self, object_key: str) -> None:
        key = self._validated_key(object_key)
        try:
            self._client.remove_object(self._bucket, key)
        except Exception as error:
            raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_FAILED) from error

    def cleanup_temporary(self, temporary_path: Path) -> None:
        path = self._validated_temporary_path(temporary_path)
        path.unlink(missing_ok=True)

    def _validated_key(self, object_key: str) -> str:
        if not object_key.startswith("instagram-sources/"):
            raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_FAILED)
        shortcode = Path(object_key).stem
        if object_key != source_object_key(shortcode):
            raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_FAILED)
        return object_key

    def _validated_temporary_path(self, temporary_path: Path) -> Path:
        path = temporary_path.resolve(strict=False)
        if self._workspace_root not in path.parents or self._temporary_root not in path.parents:
            raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_FAILED)
        if path.is_dir():
            raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_FAILED)
        return path


def _is_not_found(error: Exception) -> bool:
    return getattr(error, "code", None) in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}
