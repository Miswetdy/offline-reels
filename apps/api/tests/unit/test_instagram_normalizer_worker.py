from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.instagram import InstagramNormalizationJob, InstagramReel
from app.db.models.video import Video
from app.instagram.contracts import ReasonCode
from app.instagram.normalizer.worker import (
    InstagramNormalizerWorker,
    SourceHashMismatch,
    _classify_error,
)
from app.storage.base import ObjectMetadata, StorageObjectNotFound


class FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def stat(self, _key: str) -> ObjectMetadata:
        raise StorageObjectNotFound

    def upload_file(self, *_args) -> None:
        raise AssertionError("not used by queue-state tests")

    def download_file(self, *_args) -> None:
        raise AssertionError("not used by queue-state tests")

    def copy(self, *_args) -> None:
        raise AssertionError("not used by queue-state tests")

    def list_prefix(self, prefix: str) -> list[str]:
        return [f"{prefix}canonical.mp4"]

    def remove(self, key: str) -> None:
        self.deleted.append(key)


class BytesStorage(FakeStorage):
    def __init__(self, payload: bytes) -> None:
        super().__init__()
        self.payload = payload

    def stat(self, _key: str) -> ObjectMetadata:
        return ObjectMetadata(byte_size=len(self.payload), content_type="video/mp4")

    def download_file(self, _key: str, path) -> None:
        path.write_bytes(self.payload)


@pytest.fixture
def sessions() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def add_pending(
    sessions: sessionmaker[Session], shortcode: str = "NORMALIZER_ONE"
) -> InstagramReel:
    with sessions.begin() as session:
        reel = InstagramReel(
            shortcode=shortcode,
            canonical_url=f"https://www.instagram.com/reel/{shortcode}/",
            pipeline_status="source_ready",
            source_object_key=f"instagram-sources/{shortcode}.mp4",
            source_sha256="a" * 64,
            source_byte_size=10,
        )
        session.add(reel)
        session.flush()
        session.add(InstagramNormalizationJob(reel_id=reel.id, status="pending"))
    return reel


def test_claim_is_exclusive_between_workers(sessions: sessionmaker[Session]) -> None:
    add_pending(sessions)
    storage = FakeStorage()
    first = InstagramNormalizerWorker(sessions, storage, worker_id="worker-one")
    second = InstagramNormalizerWorker(sessions, storage, worker_id="worker-two")

    claimed = first.claim()

    assert claimed is not None
    assert second.claim() is None
    with sessions() as session:
        job = session.scalar(select(InstagramNormalizationJob))
        reel = session.scalar(select(InstagramReel))
        assert job is not None and job.status == "running" and job.attempt_count == 1
        assert reel is not None and reel.pipeline_status == "normalizing"


def test_expired_lease_becomes_terminal_history_and_one_retry(
    sessions: sessionmaker[Session],
) -> None:
    reel = add_pending(sessions)
    storage = FakeStorage()
    worker = InstagramNormalizerWorker(sessions, storage, worker_id="worker-one")
    claimed = worker.claim()
    assert claimed is not None
    with sessions.begin() as session:
        job = session.get(InstagramNormalizationJob, claimed.job_id)
        assert job is not None
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    result = worker.reconcile()

    assert result == {"stale_recovered": 1, "sources_cleaned": 0}
    assert storage.deleted == [f"{claimed.staging_prefix}/canonical.mp4"]
    with sessions() as session:
        jobs = list(
            session.scalars(
                select(InstagramNormalizationJob).order_by(InstagramNormalizationJob.created_at)
            )
        )
        current = session.get(InstagramReel, reel.id)
        assert [job.status for job in jobs] == ["failed", "pending"]
        assert jobs[0].reason_code == ReasonCode.STALE_LEASE_RECOVERED.value
        assert current is not None and current.pipeline_status == "source_ready"


def test_cancelled_worker_does_not_claim_new_work(sessions: sessionmaker[Session]) -> None:
    add_pending(sessions)
    cancelled = Event()
    cancelled.set()

    assert not InstagramNormalizerWorker(sessions, FakeStorage(), cancellation=cancelled).run_once()
    with sessions() as session:
        assert session.scalar(select(InstagramNormalizationJob.status)) == "pending"


def test_source_hash_mismatch_is_detected_before_probe(
    sessions: sessionmaker[Session], tmp_path
) -> None:
    add_pending(sessions)
    worker = InstagramNormalizerWorker(
        sessions, BytesStorage(b"0123456789"), worker_id="worker-one"
    )
    claimed = worker.claim()
    assert claimed is not None

    with pytest.raises(SourceHashMismatch):
        worker._download_and_verify_source(claimed, tmp_path / "source.mp4")


def test_ready_source_cleanup_is_reconciled_without_rolling_back_video(
    sessions: sessionmaker[Session],
) -> None:
    with sessions.begin() as session:
        video = Video(
            title="Canonical",
            object_key="videos/cleanup.mp4",
            content_type="video/mp4",
            byte_size=10,
        )
        session.add(video)
        session.flush()
        reel = InstagramReel(
            shortcode="CLEANUP_ONE",
            canonical_url="https://www.instagram.com/reel/CLEANUP_ONE/",
            pipeline_status="ready",
            source_object_key="instagram-sources/CLEANUP_ONE.mp4",
            source_sha256="b" * 64,
            source_byte_size=10,
            video_id=video.id,
            source_cleanup_pending=True,
        )
        session.add(reel)

    storage = FakeStorage()
    assert InstagramNormalizerWorker(sessions, storage).reconcile()["sources_cleaned"] == 1
    assert storage.deleted == ["instagram-sources/CLEANUP_ONE.mp4"]
    with sessions() as session:
        current = session.scalar(select(InstagramReel))
        assert current is not None and current.pipeline_status == "ready"
        assert not current.source_cleanup_pending and current.video_id is not None


@pytest.mark.parametrize(
    ("error", "reason", "retryable"),
    [
        (StorageObjectNotFound(), ReasonCode.SOURCE_MISSING, True),
        (
            RuntimeError("secret=https://private.example/token"),
            ReasonCode.MINIO_TRANSIENT_FAILURE,
            True,
        ),
    ],
)
def test_failure_classification_emits_allowlisted_codes_only(error, reason, retryable) -> None:
    actual_reason, actual_retryable = _classify_error(error)

    assert actual_reason is reason
    assert actual_retryable is retryable
    assert actual_reason.value.isascii() and " " not in actual_reason.value
