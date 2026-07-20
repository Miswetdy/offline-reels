import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.db.models.video import Video
from app.repositories.videos import VideoRepository
from app.services.video_cursor import VideoCursor
from app.storage.base import ObjectMetadata, ObjectResponse, StorageObjectNotFound, VideoStorage

CHUNK_SIZE = 64 * 1024


class VideoNotFound(Exception):
    pass


class VideoObjectNotFound(Exception):
    pass


@dataclass(frozen=True)
class StreamInfo:
    video: Video
    object_metadata: ObjectMetadata


@dataclass(frozen=True)
class SeedFile:
    path: Path
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class VideoListPage:
    items: list[Video]
    has_next_page: bool


@dataclass(frozen=True)
class SeedResult:
    video: Video
    outcome: str


def inspect_mp4_file(file_path: Path) -> SeedFile:
    if not file_path.is_file() or file_path.suffix.lower() != ".mp4":
        raise ValueError("Seed file must be an existing .mp4 file")

    digest = hashlib.sha256()
    byte_size = 0
    with file_path.open("rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            byte_size += len(chunk)
            digest.update(chunk)
    if byte_size <= 0:
        raise ValueError("Seed file must not be empty")
    return SeedFile(path=file_path, byte_size=byte_size, sha256=digest.hexdigest())


class VideoService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        repository: VideoRepository,
        storage: VideoStorage,
    ):
        self._session_factory = session_factory
        self._repository = repository
        self._storage = storage

    def list(self, limit: int, cursor: VideoCursor | None = None) -> VideoListPage:
        with self._session_factory() as session:
            rows = self._repository.list(
                session,
                limit + 1,
                before_created_at=cursor.created_at if cursor else None,
                before_id=cursor.id if cursor else None,
            )
        return VideoListPage(items=rows[:limit], has_next_page=len(rows) > limit)

    def get(self, video_id: UUID) -> Video:
        with self._session_factory() as session:
            video = self._repository.get(session, video_id)
        if video is None:
            raise VideoNotFound
        return video

    def get_stream_info(self, video_id: UUID) -> StreamInfo:
        video = self.get(video_id)
        try:
            metadata = self._storage.stat(video.object_key)
        except StorageObjectNotFound:
            raise VideoObjectNotFound from None
        return StreamInfo(video=video, object_metadata=metadata)

    def open_stream(self, object_key: str, offset: int, length: int) -> ObjectResponse:
        try:
            return self._storage.open_range(object_key, offset, length)
        except StorageObjectNotFound:
            raise VideoObjectNotFound from None

    def seed_file(self, file_path: Path, title: str | None = None) -> Video:
        return self.seed_file_with_result(file_path, title).video

    def seed_file_with_result(self, file_path: Path, title: str | None = None) -> SeedResult:
        seed_file = inspect_mp4_file(file_path)
        object_key = f"videos/{seed_file.sha256}.mp4"
        self._storage.ensure_bucket()
        object_created = False
        try:
            self._storage.stat(object_key)
        except StorageObjectNotFound:
            self._storage.upload_file(object_key, seed_file.path, "video/mp4")
            object_created = True

        with self._session_factory() as session:
            upsert_result = self._repository.upsert(
                session,
                title=title or seed_file.path.stem,
                object_key=object_key,
                content_type="video/mp4",
                byte_size=seed_file.byte_size,
            )
            session.commit()
        if object_created and upsert_result.created:
            outcome = "created"
        elif object_created or upsert_result.created:
            outcome = "restored"
        else:
            outcome = "already_existed"
        return SeedResult(video=upsert_result.video, outcome=outcome)
