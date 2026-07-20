import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.db.models.video import Video
from app.main import create_app
from app.repositories.videos import VideoRepository
from app.services.videos import VideoService


def seed_video(tmp_path: Path, session_factory, storage, content: bytes = b"0123456789"):
    file_path = tmp_path / "fixture.mp4"
    file_path.write_bytes(content)
    return VideoService(session_factory, VideoRepository(), storage).seed_file(file_path, "Fixture")


def create_video(session_factory, video_id: UUID, created_at: datetime, suffix: str) -> Video:
    with session_factory() as session:
        video = Video(
            id=video_id,
            title=f"Video {suffix}",
            object_key=f"videos/{suffix}.mp4",
            content_type="video/mp4",
            byte_size=10,
            created_at=created_at,
        )
        session.add(video)
        session.commit()
        return video


def test_migration_upgrade_and_downgrade_cycle() -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "0001_initial_schema")
    command.upgrade(config, "head")


def test_repository_and_seed_are_idempotent(tmp_path: Path, session_factory, storage) -> None:
    service = VideoService(session_factory, VideoRepository(), storage)
    file_path = tmp_path / "fixture.mp4"
    file_path.write_bytes(b"seed-data")

    first = service.seed_file(file_path, "Fixture")
    second = service.seed_file(file_path, "Changed title")

    assert first.id == second.id
    assert [video.id for video in service.list(20).items] == [first.id]
    assert storage.stat(first.object_key).byte_size == len(b"seed-data")


def test_list_detail_stream_and_cors_range(tmp_path: Path, session_factory, storage) -> None:
    video = seed_video(tmp_path, session_factory, storage)
    client = TestClient(create_app())

    listed = client.get("/videos?limit=20")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [str(video.id)]
    assert listed.json()["next_cursor"] is None

    detail = client.get(f"/videos/{video.id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Fixture"

    full = client.get(f"/videos/{video.id}/stream")
    assert full.status_code == 200
    assert full.content == b"0123456789"
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["content-length"] == "10"

    partial = client.get(
        f"/videos/{video.id}/stream",
        headers={"Range": "bytes=2-5", "Origin": "http://localhost:3000"},
    )
    assert partial.status_code == 206
    assert partial.content == b"2345"
    assert partial.headers["content-range"] == "bytes 2-5/10"
    assert partial.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "Content-Range" in partial.headers["access-control-expose-headers"]

    preflight = client.options(
        f"/videos/{video.id}/stream",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Range",
        },
    )
    assert preflight.status_code == 200
    assert "range" in preflight.headers["access-control-allow-headers"].lower()

    rejected = client.options(
        f"/videos/{video.id}/stream",
        headers={"Origin": "http://untrusted.example", "Access-Control-Request-Method": "GET"},
    )
    assert rejected.status_code == 400


def test_rejects_invalid_range_and_missing_video(tmp_path: Path, session_factory, storage) -> None:
    video = seed_video(tmp_path, session_factory, storage)
    client = TestClient(create_app())

    response = client.get(f"/videos/{video.id}/stream", headers={"Range": "bytes=0-1,3-4"})
    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"

    missing = client.get(f"/videos/{UUID(int=0)}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "video_not_found"


def test_missing_object_is_safe_error(tmp_path: Path, session_factory, storage) -> None:
    video = seed_video(tmp_path, session_factory, storage)
    storage.remove(video.object_key)
    client = TestClient(create_app())

    response = client.get(f"/videos/{video.id}/stream")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "video_object_not_found"


def test_stream_range_bodies_match_real_minio_object(
    tmp_path: Path,
    session_factory,
    storage,
) -> None:
    content = bytes(range(256)) * 1024
    video = seed_video(tmp_path, session_factory, storage, content)
    client = TestClient(create_app())

    full = client.get(f"/videos/{video.id}/stream")
    assert full.status_code == 200
    assert full.content == content
    assert hashlib.sha256(full.content).hexdigest() == hashlib.sha256(content).hexdigest()

    open_ended = client.get(f"/videos/{video.id}/stream", headers={"Range": "bytes=1024-"})
    assert open_ended.status_code == 206
    assert open_ended.content == content[1024:]
    assert open_ended.headers["content-length"] == str(len(content) - 1024)

    suffix = client.get(f"/videos/{video.id}/stream", headers={"Range": "bytes=-65536"})
    explicit = client.get(
        f"/videos/{video.id}/stream",
        headers={"Range": f"bytes={len(content) - 65536}-{len(content) - 1}"},
    )
    assert suffix.status_code == explicit.status_code == 206
    assert suffix.content == explicit.content == content[-65536:]

    clipped = client.get(
        f"/videos/{video.id}/stream",
        headers={"Range": f"bytes={len(content) - 512}-{len(content) + 4096}"},
    )
    assert clipped.status_code == 206
    assert clipped.content == content[-512:]
    assert clipped.headers["content-range"] == (
        f"bytes {len(content) - 512}-{len(content) - 1}/{len(content)}"
    )


def test_keyset_pagination_orders_equal_timestamps_without_duplicates(session_factory) -> None:
    newest = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
    shared = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    oldest = datetime(2026, 7, 20, 11, 0, tzinfo=UTC)
    expected_ids = [UUID(int=value) for value in (4, 3, 2, 1)]
    create_video(session_factory, expected_ids[0], newest, "newest")
    create_video(session_factory, expected_ids[1], shared, "shared-high")
    create_video(session_factory, expected_ids[2], shared, "shared-low")
    create_video(session_factory, expected_ids[3], oldest, "oldest")
    client = TestClient(create_app())

    first = client.get("/videos?limit=2")
    assert first.status_code == 200
    first_body = first.json()
    assert [item["id"] for item in first_body["items"]] == [
        str(video_id) for video_id in expected_ids[:2]
    ]
    assert first_body["next_cursor"] is not None

    second = client.get("/videos", params={"limit": 2, "cursor": first_body["next_cursor"]})
    assert second.status_code == 200
    second_body = second.json()
    assert [item["id"] for item in second_body["items"]] == [
        str(video_id) for video_id in expected_ids[2:]
    ]
    assert second_body["next_cursor"] is None

    returned_ids = [item["id"] for item in first_body["items"] + second_body["items"]]
    assert returned_ids == [str(video_id) for video_id in expected_ids]
    assert len(returned_ids) == len(set(returned_ids))


def test_pagination_limit_bounds_end_and_invalid_cursor(session_factory) -> None:
    timestamp = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    create_video(session_factory, UUID(int=1), timestamp, "one")
    client = TestClient(create_app())

    for limit in (1, 10, 30):
        response = client.get("/videos", params={"limit": limit})
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        assert response.json()["next_cursor"] is None

    assert client.get("/videos?limit=0").status_code == 422
    assert client.get("/videos?limit=31").status_code == 422
    invalid_cursor = client.get("/videos?cursor=not-a-valid-cursor")
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json() == {
        "detail": {"code": "invalid_cursor", "message": "Cursor is invalid."}
    }
