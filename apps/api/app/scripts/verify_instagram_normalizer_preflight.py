"""Read-only Stage 5 smoke aggregate check, compatible before migration 0006."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.settings import get_settings
from app.db.session import create_session_factory
from app.storage.base import StorageObjectNotFound
from app.storage.minio import MinioVideoStorage


def main() -> int:
    settings = get_settings()
    storage = MinioVideoStorage(settings)
    try:
        with create_session_factory(settings)() as session:
            counts = session.execute(
                text(
                    """
                    SELECT
                      count(*) FILTER (WHERE pipeline_status = 'source_ready') AS source_ready,
                      (SELECT count(*) FROM instagram_normalization_jobs WHERE status = 'pending')
                        AS pending,
                      (SELECT count(*) FROM videos) AS videos
                    FROM instagram_reels
                    """
                )
            ).one()
            source_keys = list(
                session.scalars(
                    text(
                        """
                        SELECT source_object_key FROM instagram_reels
                        WHERE pipeline_status = 'source_ready' AND source_object_key IS NOT NULL
                        """
                    )
                )
            )
    except SQLAlchemyError:
        print(json.dumps({"event": "failed", "reason_code": "POSTGRES_COMMIT_FAILURE"}))
        return 1
    try:
        source_objects = len(storage.list_prefix("instagram-sources/"))
        missing_sources = sum(not _object_exists(storage, key) for key in source_keys)
    except Exception:
        print(json.dumps({"event": "failed", "reason_code": "MINIO_TRANSIENT_FAILURE"}))
        return 1
    print(
        json.dumps(
            {
                "source_ready": int(counts.source_ready),
                "pending": int(counts.pending),
                "source_objects": source_objects,
                "videos": int(counts.videos),
                "missing_source_ready_objects": missing_sources,
            },
            sort_keys=True,
        )
    )
    return 0


def _object_exists(storage: MinioVideoStorage, key: str) -> bool:
    try:
        storage.stat(key)
    except StorageObjectNotFound:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
