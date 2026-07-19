from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class StorageObjectNotFound(Exception):
    pass


@dataclass(frozen=True)
class ObjectMetadata:
    byte_size: int
    content_type: str


class ObjectResponse(Protocol):
    def stream(self, amt: int = 65536): ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class VideoStorage(Protocol):
    def ensure_bucket(self) -> None: ...

    def stat(self, object_key: str) -> ObjectMetadata: ...

    def upload_file(self, object_key: str, file_path: Path, content_type: str) -> None: ...

    def open_range(self, object_key: str, offset: int, length: int) -> ObjectResponse: ...

    def remove(self, object_key: str) -> None: ...
