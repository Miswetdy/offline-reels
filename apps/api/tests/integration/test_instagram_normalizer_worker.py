import hashlib
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models.instagram import InstagramNormalizationJob, InstagramReel
from app.instagram.normalizer.worker import InstagramNormalizerWorker, _is_worker_canonical
from app.main import create_app
from app.media.compatibility import is_canonical_media
from app.media.normalize import normalize_video
from app.media.probe import probe_media


def create_h264_aac_fixture(path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg must be available in the integration image")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=44100",
            "-t",
            "1",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def test_real_minio_postgres_normalization_publishes_catalog_video(
    tmp_path: Path, session_factory, storage
) -> None:
    source = tmp_path / "source.mp4"
    create_h264_aac_fixture(source)
    source_probe = probe_media(source)
    assert source_probe.audio_codecs == ("aac",)
    assert is_canonical_media(source_probe)
    assert _is_worker_canonical(source_probe)
    with normalize_video(source) as normalized:
        assert normalized.probe.audio_codecs == ("aac",)
        assert is_canonical_media(normalized.probe)
        assert _is_worker_canonical(normalized.probe)
    source_bytes = source.read_bytes()
    source_key = "instagram-sources/NORMALIZER_REAL_ONE.mp4"
    storage.upload_file(source_key, source, "video/mp4")
    with session_factory.begin() as session:
        reel = InstagramReel(
            shortcode="NORMALIZER_REAL_ONE",
            canonical_url="https://www.instagram.com/reel/NORMALIZER_REAL_ONE/",
            pipeline_status="source_ready",
            source_object_key=source_key,
            source_sha256=hashlib.sha256(source_bytes).hexdigest(),
            source_byte_size=len(source_bytes),
        )
        session.add(reel)
        session.flush()
        session.add(InstagramNormalizationJob(reel_id=reel.id, status="pending"))

    events: list[dict[str, object]] = []
    worker = InstagramNormalizerWorker(
        session_factory,
        storage,
        worker_id="integration-worker",
        progress=events.append,
    )
    assert worker.run_once()
    assert not worker.run_once()

    with session_factory() as session:
        stored_reel = session.scalar(select(InstagramReel))
        job = session.scalar(select(InstagramNormalizationJob))
        assert stored_reel is not None and stored_reel.pipeline_status == "ready", (
            stored_reel.failure_reason_code,
            events,
        )
        assert stored_reel.video_id is not None and not stored_reel.source_cleanup_pending
        assert job is not None and job.status == "completed" and job.attempt_count == 1

    # The storage adapter raises a typed miss; do not turn a missing source into
    # an API-visible error after ready publication.
    from app.storage.base import StorageObjectNotFound

    try:
        storage.stat(source_key)
    except StorageObjectNotFound:
        pass
    else:
        raise AssertionError("successful normalization must clean its source object")
    client = TestClient(create_app())
    catalog = client.get("/videos")
    assert catalog.status_code == 200 and len(catalog.json()["items"]) == 1
    assert {event["event"] for event in events} >= {"claimed", "db_committed", "completed"}
    assert storage.list_prefix("instagram-normalizer-staging/") == []
