from uuid import UUID

from sqlalchemy import Select, desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.video import Video


class VideoRepository:
    def list(self, session: Session, limit: int) -> list[Video]:
        statement: Select[tuple[Video]] = (
            select(Video).order_by(desc(Video.created_at), desc(Video.id)).limit(limit)
        )
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
    ) -> Video:
        statement = (
            insert(Video)
            .values(
                title=title,
                object_key=object_key,
                content_type=content_type,
                byte_size=byte_size,
            )
            .on_conflict_do_nothing(index_elements=[Video.object_key])
            .returning(Video)
        )
        created = session.scalar(statement)
        if created is not None:
            return created

        existing = session.scalar(select(Video).where(Video.object_key == object_key))
        if existing is None:
            raise RuntimeError("video upsert did not return a record")
        return existing
