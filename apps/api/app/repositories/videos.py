from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, desc, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.video import Video


@dataclass(frozen=True)
class VideoUpsertResult:
    video: Video
    created: bool


class VideoRepository:
    def list(
        self,
        session: Session,
        limit: int,
        *,
        before_created_at: datetime | None = None,
        before_id: UUID | None = None,
    ) -> list[Video]:
        statement: Select[tuple[Video]] = select(Video)
        if before_created_at is not None and before_id is not None:
            statement = statement.where(
                or_(
                    Video.created_at < before_created_at,
                    and_(Video.created_at == before_created_at, Video.id < before_id),
                )
            )
        statement = statement.order_by(desc(Video.created_at), desc(Video.id)).limit(limit)
        return list(session.scalars(statement))

    def get(self, session: Session, video_id: UUID) -> Video | None:
        return session.get(Video, video_id)

    def upsert(
        self,
        session: Session,
        *,
        title: str,
        object_key: str,
        content_type: str,
        byte_size: int,
        normalization_strategy: str | None = None,
        original_video_codec: str | None = None,
        normalized_video_codec: str | None = None,
        width: int | None = None,
        height: int | None = None,
        duration_ms: int | None = None,
        file_size_bytes: int | None = None,
        has_audio: bool | None = None,
        normalized_at: datetime | None = None,
    ) -> VideoUpsertResult:
        statement = (
            insert(Video)
            .values(
                title=title,
                object_key=object_key,
                content_type=content_type,
                byte_size=byte_size,
                normalization_strategy=normalization_strategy,
                original_video_codec=original_video_codec,
                normalized_video_codec=normalized_video_codec,
                width=width,
                height=height,
                duration_ms=duration_ms,
                file_size_bytes=file_size_bytes,
                has_audio=has_audio,
                normalized_at=normalized_at,
            )
            .on_conflict_do_nothing(index_elements=[Video.object_key])
            .returning(Video)
        )
        created = session.scalar(statement)
        if created is not None:
            return VideoUpsertResult(video=created, created=True)

        existing = session.scalar(select(Video).where(Video.object_key == object_key))
        if existing is None:
            raise RuntimeError("video upsert did not return a record")
        return VideoUpsertResult(video=existing, created=False)
