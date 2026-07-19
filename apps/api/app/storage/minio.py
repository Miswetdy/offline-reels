from pathlib import Path
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.core.settings import Settings
from app.storage.base import ObjectMetadata, ObjectResponse, StorageObjectNotFound


class MinioVideoStorage:
    def __init__(self, settings: Settings):
        endpoint = urlparse(str(settings.minio_endpoint))
        self._bucket = settings.minio_bucket
        self._client = Minio(
            endpoint.netloc,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=endpoint.scheme == "https",
        )

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            try:
                self._client.make_bucket(self._bucket)
            except S3Error as error:
                if error.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                    raise

    def stat(self, object_key: str) -> ObjectMetadata:
        try:
            result = self._client.stat_object(self._bucket, object_key)
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise StorageObjectNotFound from None
            raise
        return ObjectMetadata(
            byte_size=result.size,
            content_type=result.content_type or "video/mp4",
        )

    def upload_file(self, object_key: str, file_path: Path, content_type: str) -> None:
        self._client.fput_object(
            self._bucket,
            object_key,
            str(file_path),
            content_type=content_type,
        )

    def open_range(self, object_key: str, offset: int, length: int) -> ObjectResponse:
        try:
            return self._client.get_object(self._bucket, object_key, offset=offset, length=length)
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise StorageObjectNotFound from None
            raise

    def remove(self, object_key: str) -> None:
        self._client.remove_object(self._bucket, object_key)
