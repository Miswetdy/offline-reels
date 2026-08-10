"""Read-only end-to-end Stage 5 smoke audit without claiming jobs."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.settings import get_settings
from app.db.models.instagram import InstagramNormalizationJob, InstagramReel
from app.db.models.video import Video
from app.db.session import create_session_factory
from app.instagram.normalizer.worker import STAGING_PREFIX
from app.main import create_app
from app.media.compatibility import is_canonical_media
from app.media.normalize import validate_decode
from app.media.probe import probe_media
from app.storage.base import StorageObjectNotFound
from app.storage.minio import MinioVideoStorage


def main() -> int:
    try:
        settings = get_settings()
        sessions = create_session_factory(settings)
        storage = MinioVideoStorage(settings)
        with sessions() as session:
            rows = list(
                session.execute(
                    select(Video.object_key, Video.byte_size, Video.content_sha256)
                    .join(InstagramReel, InstagramReel.video_id == Video.id)
                    .where(InstagramReel.pipeline_status == "ready")
                )
            )
            report = {
                "ready": _count(session, InstagramReel.pipeline_status == "ready"),
                "completed": _count(
                    session,
                    InstagramNormalizationJob.status == "completed",
                    table=InstagramNormalizationJob,
                ),
                "pending": _count(
                    session,
                    InstagramNormalizationJob.status == "pending",
                    table=InstagramNormalizationJob,
                ),
                "running": _count(
                    session,
                    InstagramNormalizationJob.status == "running",
                    table=InstagramNormalizationJob,
                ),
                "failed": _count(
                    session,
                    InstagramNormalizationJob.status == "failed",
                    table=InstagramNormalizationJob,
                ),
                "videos": _count(session, None, table=Video),
                "cleanup_pending": _count(session, InstagramReel.source_cleanup_pending.is_(True)),
                "active_leases": _count(
                    session,
                    InstagramNormalizationJob.lease_expires_at.is_not(None),
                    table=InstagramNormalizationJob,
                ),
                "ready_missing_video_id": _count(
                    session,
                    (InstagramReel.pipeline_status == "ready")
                    & InstagramReel.video_id.is_(None),
                ),
            }
        final_matches = _verify_final_objects(storage, rows)
        media_matches = _verify_one_media(storage, rows)
        catalog = TestClient(create_app()).get("/videos?limit=30")
        report.update(
            {
                "final_objects": len(storage.list_prefix("videos/")),
                "source_objects": len(storage.list_prefix("instagram-sources/")),
                "staging_objects": len(storage.list_prefix(f"{STAGING_PREFIX}/")),
                "sha_size_matches": final_matches,
                "catalog_status_code": catalog.status_code,
                "catalog_items": len(catalog.json().get("items", []))
                if catalog.status_code == 200
                else 0,
                "media_verified": media_matches,
                "planning_noop": report["pending"] == 0 and report["running"] == 0,
            }
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"event": "failed", "reason_code": "POSTGRES_COMMIT_FAILURE"}))
        return 1


def _count(session, criterion, *, table=InstagramReel) -> int:
    statement = select(func.count()).select_from(table)
    if criterion is not None:
        statement = statement.where(criterion)
    return int(session.scalar(statement) or 0)


def _verify_final_objects(
    storage: MinioVideoStorage, rows: list[tuple[str, int, str | None]]
) -> int:
    matches = 0
    with tempfile.TemporaryDirectory(prefix="offline-reels-audit-") as directory:
        for index, (key, expected_size, expected_sha256) in enumerate(rows):
            if expected_sha256 is None:
                continue
            path = Path(directory) / f"{index}.mp4"
            try:
                metadata = storage.stat(key)
                storage.download_file(key, path)
            except StorageObjectNotFound:
                continue
            if metadata.byte_size != expected_size:
                continue
            if _sha256(path) == expected_sha256:
                matches += 1
    return matches


def _verify_one_media(storage: MinioVideoStorage, rows: list[tuple[str, int, str | None]]) -> bool:
    if not rows:
        return False
    with tempfile.TemporaryDirectory(prefix="offline-reels-audit-") as directory:
        path = Path(directory) / "canonical.mp4"
        storage.download_file(rows[0][0], path)
        probe = probe_media(path)
        validate_decode(path)
    return bool(probe.audio_codecs) and is_canonical_media(probe)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
