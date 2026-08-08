"""Opt-in disposable PostgreSQL/MinIO integration for Stage 3C.1 continuation."""

import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from minio import Minio
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.models.instagram import InstagramAccount, InstagramCollectionRun, InstagramReel
from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.fixtures import FixtureRollbackFailingPersistence
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.collector.runtime.minio_storage import MinioCollectorSourceStorage
from app.instagram.collector.runtime.stage3c1 import prepare_stage3c1
from app.instagram.collector.runtime.validator import FfprobeSourceValidator
from app.instagram.collector.service import CollectorEngine, CollectorLimits
from app.instagram.contracts import AccountStatus, CollectionTrigger


def test_real_postgresql_minio_stage3c1_continuation(tmp_path: Path) -> None:
    configuration = _configuration()
    if configuration is None:
        pytest.skip("requires disposable Stage 3C.1 PostgreSQL/MinIO environment")
    database_url, endpoint, access_key, secret_key, bucket = configuration
    source = tmp_path / "synthetic.mp4"
    _make_mp4(source)
    sessions = sessionmaker(
        bind=create_engine(database_url), autoflush=False, expire_on_commit=False
    )
    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    account_id = uuid4()
    with sessions.begin() as session:
        session.add(InstagramAccount(id=account_id, status=AccountStatus.CONNECTED.value))
    persistence = CollectorPersistence(sessions)
    workspace = tmp_path / "workspace"

    seed = _collector(sessions, client, bucket, workspace, source, _codes("SEED", 3)).collect(
        account_id, CollectionTrigger.MANUAL, 3
    )
    assert seed.status == "completed"
    assert persistence.account_durable_count(account_id) == 3

    continuation_feed = _CountingFeed(_codes("NEW", 7))
    continuation = _collector(
        sessions, client, bucket, workspace, source, continuation_feed
    ).collect(account_id, CollectionTrigger.MANUAL, 7, desired_account_total=10)
    assert continuation.status == "completed"
    assert continuation.source_committed_count == 7
    assert continuation.already_available_count == 0
    assert continuation_feed.advance_calls == 6
    assert persistence.account_durable_count(account_id) == 10
    plan = prepare_stage3c1(persistence, account_id, client, bucket, 10)
    assert plan.initial_durable_count == 10 and plan.remaining == 0
    with sessions() as session:
        run_count = int(
            session.scalar(select(func.count()).select_from(InstagramCollectionRun)) or 0
        )
    assert prepare_stage3c1(persistence, account_id, client, bucket, 10).remaining == 0
    with sessions() as session:
        assert (
            int(session.scalar(select(func.count()).select_from(InstagramCollectionRun)) or 0)
            == run_count
        )
        reels = session.scalars(select(InstagramReel)).all()
        assert len(reels) == 10
        assert all(
            reel.source_object_key and reel.source_sha256 and reel.source_byte_size
            for reel in reels
        )
    assert {
        item.object_name
        for item in client.list_objects(bucket, prefix="instagram-sources/", recursive=True)
    } == {item.object_key for item in persistence.account_durable_baseline(account_id)}


def test_real_stage3c1_available_duplicate_and_upload_compensation(tmp_path: Path) -> None:
    configuration = _configuration()
    if configuration is None:
        pytest.skip("requires disposable Stage 3C.1 PostgreSQL/MinIO environment")
    database_url, endpoint, access_key, secret_key, bucket = configuration
    source = tmp_path / "synthetic.mp4"
    _make_mp4(source)
    sessions = sessionmaker(
        bind=create_engine(database_url), autoflush=False, expire_on_commit=False
    )
    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    primary, other = uuid4(), uuid4()
    with sessions.begin() as session:
        session.add_all(
            [
                InstagramAccount(id=primary, status=AccountStatus.CONNECTED.value),
                InstagramAccount(id=other, status=AccountStatus.CONNECTED.value),
            ]
        )
    workspace = tmp_path / "workspace"
    _collector(sessions, client, bucket, workspace, source, _codes("OWNED", 1)).collect(
        primary, CollectionTrigger.MANUAL, 1
    )
    global_candidate = _codes("GLOBAL", 1)
    _collector(sessions, client, bucket, workspace, source, global_candidate).collect(
        other, CollectionTrigger.MANUAL, 1
    )
    downloader = _CopyingDownloader(source)
    available = _collector(
        sessions, client, bucket, workspace, source, global_candidate, downloader=downloader
    ).collect(primary, CollectionTrigger.MANUAL, 1, desired_account_total=2)
    assert available.status == "completed" and available.already_available_count == 1
    assert downloader.calls == 0
    duplicate = _collector(
        sessions, client, bucket, workspace, source, _codes("OWNED", 1), downloader=downloader
    ).collect(primary, CollectionTrigger.MANUAL, 1, desired_account_total=3)
    assert duplicate.status == "failed" and duplicate.duplicate_skipped_count == 1
    assert downloader.calls == 0

    failing_candidate = _codes("COMPENSATE", 1)[0]
    failing = CollectorEngine(
        FixtureRollbackFailingPersistence(sessions),
        _CountingFeed([failing_candidate]),
        _CopyingDownloader(source),
        FfprobeSourceValidator(workspace, 10 * 1024 * 1024),
        MinioCollectorSourceStorage(client, bucket, workspace, 10 * 1024 * 1024),
        limits=CollectorLimits(max_target=1),
    ).collect(other, CollectionTrigger.MANUAL, 1)
    assert failing.status == "failed"
    assert failing.stop_reason_code == "DATABASE_WRITE_FAILED"
    assert not any(
        item.object_name == "instagram-sources/COMPENSATE_1.mp4"
        for item in client.list_objects(bucket, prefix="instagram-sources/", recursive=True)
    )


def _collector(
    sessions, client, bucket: str, workspace: Path, source: Path, candidates, *, downloader=None
):
    feed = candidates if hasattr(candidates, "current") else _CountingFeed(candidates)
    return CollectorEngine(
        CollectorPersistence(sessions),
        feed,
        downloader or _CopyingDownloader(source),
        FfprobeSourceValidator(workspace, 10 * 1024 * 1024),
        MinioCollectorSourceStorage(client, bucket, workspace, 10 * 1024 * 1024),
        limits=CollectorLimits(
            max_target=10,
            max_advances=29,
            max_transition_operations=29,
            max_scroll_actions=58,
            max_observations=30,
            max_run_bytes=10 * 1024 * 1024,
        ),
        sleep=lambda _seconds: None,
    )


def _codes(prefix: str, count: int) -> list[ReelCandidate]:
    return [
        ReelCandidate(f"{prefix}_{index}", f"https://www.instagram.com/reel/{prefix}_{index}/")
        for index in range(1, count + 1)
    ]


class _CountingFeed:
    def __init__(self, candidates: list[ReelCandidate]) -> None:
        from app.instagram.collector.fixtures import FixtureFeed

        self._delegate = FixtureFeed(candidates)
        self.advance_calls = 0

    def current(self):
        return self._delegate.current()

    def pause_current(self) -> None:
        self._delegate.pause_current()

    def advance(self) -> None:
        self.advance_calls += 1
        self._delegate.advance()

    def wait_for_next(self, previous_shortcode, should_stop=None):
        return self._delegate.wait_for_next(previous_shortcode, should_stop)

    @property
    def transition_diagnostics(self):
        return self._delegate.transition_diagnostics

    @property
    def scroll_target_diagnostics(self):
        return self._delegate.scroll_target_diagnostics

    def close(self) -> None:
        self._delegate.close()


class _CopyingDownloader:
    def __init__(self, source: Path) -> None:
        self._source = source
        self.calls = 0

    def download(self, candidate: ReelCandidate, temporary_path: Path) -> None:
        del candidate
        self.calls += 1
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._source, temporary_path)


def _configuration() -> tuple[str, str, str, str, str] | None:
    values = tuple(
        os.environ.get(key)
        for key in (
            "COLLECTOR_STAGE3C1_IT_DATABASE_URL",
            "COLLECTOR_STAGE3C1_IT_MINIO_ENDPOINT",
            "COLLECTOR_STAGE3C1_IT_MINIO_ACCESS_KEY",
            "COLLECTOR_STAGE3C1_IT_MINIO_SECRET_KEY",
            "COLLECTOR_STAGE3C1_IT_MINIO_BUCKET",
        )
    )
    return values if all(isinstance(value, str) and value for value in values) else None


def _make_mp4(path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is required for real Collector infrastructure integration")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=64x64:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "0.5",
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
