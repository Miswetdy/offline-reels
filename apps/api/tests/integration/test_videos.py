from pathlib import Path

from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.main import create_app
from app.repositories.videos import VideoRepository
from app.services.videos import VideoService


def seed_video(tmp_path: Path, session_factory, storage, content: bytes = b"0123456789"):
    file_path = tmp_path / "fixture.mp4"
    file_path.write_bytes(content)
    return VideoService(session_factory, VideoRepository(), storage).seed_file(file_path, "Fixture")


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
    assert [video.id for video in service.list(20)] == [first.id]
    assert storage.stat(first.object_key).byte_size == len(b"seed-data")


def test_list_detail_stream_and_cors_range(tmp_path: Path, session_factory, storage) -> None:
    video = seed_video(tmp_path, session_factory, storage)
    client = TestClient(create_app())

    listed = client.get("/videos?limit=20")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [str(video.id)]

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

    missing = client.get("/videos/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "video_not_found"


def test_missing_object_is_safe_error(tmp_path: Path, session_factory, storage) -> None:
    video = seed_video(tmp_path, session_factory, storage)
    storage.remove(video.object_key)
    client = TestClient(create_app())

    response = client.get(f"/videos/{video.id}/stream")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "video_object_not_found"
