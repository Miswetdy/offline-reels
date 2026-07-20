from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.videos import StreamInfo, VideoListPage, VideoNotFound, VideoObjectNotFound
from app.storage.base import ObjectMetadata


class FakeResponse:
    def __init__(self):
        self.closed = False
        self.released = False

    def stream(self, _amount: int):
        yield b"0123456789"

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeVideo:
    def __init__(self):
        self.id = uuid4()
        self.title = "Test"
        self.object_key = "videos/test.mp4"
        self.content_type = "video/mp4"
        self.byte_size = 10
        self.created_at = datetime.now(UTC)


class FakeVideoService:
    def __init__(self):
        self.video = FakeVideo()
        self.response = FakeResponse()

    def list(self, _limit: int, _cursor=None):
        return VideoListPage(items=[self.video], has_next_page=False)

    def get(self, video_id):
        if video_id != self.video.id:
            raise VideoNotFound
        return self.video

    def get_stream_info(self, video_id):
        return StreamInfo(video=self.get(video_id), object_metadata=ObjectMetadata(10, "video/mp4"))

    def open_stream(self, _object_key: str, _offset: int, _length: int):
        return self.response


def test_stream_closes_and_releases_upstream_response() -> None:
    app = create_app()
    service = FakeVideoService()
    app.state.video_service = service
    client = TestClient(app)

    response = client.get(f"/videos/{service.video.id}/stream", headers={"Range": "bytes=2-5"})

    assert response.status_code == 206
    assert response.content == b"0123456789"
    assert service.response.closed
    assert service.response.released


def test_list_uses_paginated_contract_and_rejects_invalid_cursor() -> None:
    app = create_app()
    service = FakeVideoService()
    app.state.video_service = service
    client = TestClient(app)

    listed = client.get("/videos?limit=10")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == str(service.video.id)
    assert listed.json()["next_cursor"] is None

    invalid_cursor = client.get("/videos?cursor=not-a-valid-cursor")
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json() == {
        "detail": {"code": "invalid_cursor", "message": "Cursor is invalid."}
    }


def test_list_validates_limit() -> None:
    app = create_app()
    app.state.video_service = FakeVideoService()
    client = TestClient(app)

    assert client.get("/videos?limit=0").status_code == 422
    assert client.get("/videos?limit=31").status_code == 422


def test_stream_returns_safe_missing_object_error() -> None:
    app = create_app()
    service = FakeVideoService()

    def missing(_video_id):
        raise VideoObjectNotFound

    service.get_stream_info = missing
    app.state.video_service = service
    response = TestClient(app).get(f"/videos/{service.video.id}/stream")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "video_object_not_found"
