import json
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models.video import Video
from app.main import create_app
from app.media.errors import MediaProbeError
from app.media.probe import probe_media
from app.repositories.videos import VideoRepository
from app.services.videos import VideoService
from app.storage.base import StorageObjectNotFound


class TrackingStorage:
    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self.uploaded_keys: list[str] = []
        self.removed_keys: list[str] = []

    def ensure_bucket(self) -> None:
        self._delegate.ensure_bucket()

    def stat(self, object_key: str):
        return self._delegate.stat(object_key)

    def upload_file(self, object_key: str, file_path: Path, content_type: str) -> None:
        self.uploaded_keys.append(object_key)
        self._delegate.upload_file(object_key, file_path, content_type)

    def remove(self, object_key: str) -> None:
        self.removed_keys.append(object_key)
        self._delegate.remove(object_key)


class FailingCommitSession:
    def __init__(self, session) -> None:
        self._session = session

    def __getattr__(self, name: str):
        return getattr(self._session, name)

    def commit(self) -> None:
        self._session.rollback()
        raise RuntimeError("database unavailable")

    def rollback(self) -> None:
        self._session.rollback()


def run_ffmpeg(*arguments: str) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.fail("The API image must provide ffmpeg for seed normalization.")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *arguments], check=True)


def create_fixture(path: Path, codec: str) -> None:
    encoder = "libx264" if codec == "h264" else "libvpx-vp9"
    run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=128x72:rate=24",
        "-t",
        "2",
        "-c:v",
        encoder,
        "-pix_fmt",
        "yuv420p",
        str(path),
    )


@pytest.mark.parametrize(
    ("source_codec", "strategy"),
    [("h264", "passthrough"), ("vp9", "transcode")],
)
def test_seed_normalizes_media_persists_metadata_and_preserves_stream_contract(
    tmp_path: Path,
    session_factory,
    storage,
    source_codec: str,
    strategy: str,
) -> None:
    source = tmp_path / f"source-{source_codec}.mp4"
    create_fixture(source, source_codec)
    service = VideoService(session_factory, VideoRepository(), storage)

    result = service.seed_file_with_result(source, f"{source_codec} fixture")
    video = result.video

    assert result.normalized_media.strategy.value == strategy
    assert video.object_key.endswith(".mp4")
    assert video.content_type == "video/mp4"
    assert video.normalization_strategy == strategy
    assert video.original_video_codec == source_codec
    assert video.normalized_video_codec == "h264"
    assert video.width and video.width > 0
    assert video.height and video.height > 0
    assert video.duration_ms and video.duration_ms > 0
    assert video.file_size_bytes == video.byte_size
    assert video.has_audio is False
    assert video.normalized_at is not None
    assert storage.stat(video.object_key).content_type == "video/mp4"

    client = TestClient(create_app())
    catalog = client.get("/videos?limit=20")
    assert catalog.status_code == 200
    assert str(video.id) in [item["id"] for item in catalog.json()["items"]]

    full = client.get(f"/videos/{video.id}/stream")
    assert full.status_code == 200
    downloaded = tmp_path / f"downloaded-{source_codec}.mp4"
    downloaded.write_bytes(full.content)
    probe = probe_media(downloaded)
    assert probe.video_codec == "h264"
    assert probe.pixel_format == "yuv420p"
    assert probe.audio_codecs == ()

    partial = client.get(f"/videos/{video.id}/stream", headers={"Range": "bytes=0-1023"})
    assert partial.status_code == 206
    assert partial.headers["content-length"] == "1024"
    invalid = client.get(f"/videos/{video.id}/stream", headers={"Range": "bytes=0-1,3-4"})
    assert invalid.status_code == 416

    persisted = VideoService(session_factory, VideoRepository(), storage).get(video.id)
    assert persisted.object_key == video.object_key
    assert storage.stat(persisted.object_key).byte_size == video.byte_size


def test_corrupt_seed_creates_no_database_record_or_media_object(
    tmp_path: Path,
    session_factory,
    storage,
) -> None:
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not a video")
    service = VideoService(session_factory, VideoRepository(), storage)

    with pytest.raises(MediaProbeError):
        service.seed_file_with_result(corrupt)

    with session_factory() as session:
        assert list(session.scalars(select(Video))) == []


def test_commit_failure_rolls_back_database_and_removes_only_new_media_object(
    tmp_path: Path,
    session_factory,
    storage,
) -> None:
    source = tmp_path / "source-h264.mp4"
    existing = tmp_path / "existing.mp4"
    create_fixture(source, "h264")
    create_fixture(existing, "h264")
    existing_key = "videos/existing-object.mp4"
    storage.upload_file(existing_key, existing, "video/mp4")
    tracked_storage = TrackingStorage(storage)

    @contextmanager
    def failing_session_factory():
        session = session_factory()
        try:
            yield FailingCommitSession(session)
        finally:
            session.close()

    service = VideoService(failing_session_factory, VideoRepository(), tracked_storage)
    try:
        with pytest.raises(RuntimeError, match="database unavailable"):
            service.seed_file_with_result(source)

        assert len(tracked_storage.uploaded_keys) == 1
        new_key = tracked_storage.uploaded_keys[0]
        assert new_key != existing_key
        assert tracked_storage.removed_keys == [new_key]
        storage.stat(existing_key)
        with pytest.raises(StorageObjectNotFound):
            storage.stat(new_key)
        with session_factory() as session:
            assert list(session.scalars(select(Video))) == []
    finally:
        storage.remove(existing_key)


def test_seed_cli_json_exposes_normalization_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source-vp9.mp4"
    create_fixture(source, "vp9")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.scripts.seed_video",
            "--file",
            str(source),
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.stderr == ""
    assert completed.stdout == f"{json.dumps(payload)}\n"
    assert payload["id"]
    assert payload["normalization_strategy"] == "transcode"
    assert payload["original_codec"] == "vp9"
    assert payload["normalized_codec"] == "h264"
    assert payload["file_size_bytes"] > 0
    assert payload["has_audio"] is False
