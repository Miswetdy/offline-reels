"""Opt-in disposable PostgreSQL/MinIO integration for the Stage 3B core."""

import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from minio import Minio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models.instagram import InstagramAccount, InstagramCollectionRun, InstagramReel
from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.fixtures import FixtureFeed
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.minio_storage import MinioCollectorSourceStorage
from app.instagram.collector.runtime.operator import SafeEventTranscript
from app.instagram.collector.runtime.validator import FfprobeSourceValidator
from app.instagram.collector.runtime.verification import (
    CollectorPostRunVerifier,
    capture_run_baseline,
)
from app.instagram.collector.service import CollectorEngine, CollectorLimits
from app.instagram.contracts import AccountStatus, CollectionTrigger


def test_real_postgresql_minio_three_source_commits(tmp_path: Path) -> None:
    configuration = _integration_configuration()
    if configuration is None:
        pytest.skip("requires disposable Stage 3B PostgreSQL/MinIO environment")
    database_url, minio_endpoint, minio_access_key, minio_secret_key, minio_bucket = configuration
    source = tmp_path / "fixture.mp4"
    _make_mp4(source)
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    account_id = uuid4()
    with sessions.begin() as session:
        session.add(InstagramAccount(id=account_id, status=AccountStatus.CONNECTED.value))
    client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=False,
    )
    if not client.bucket_exists(minio_bucket):
        client.make_bucket(minio_bucket)
    candidates = [
        ReelCandidate(code, f"https://www.instagram.com/reel/{code}/")
        for code in ("IT_STAGE3B_ONE", "IT_STAGE3B_TWO", "IT_STAGE3B_THREE")
    ]
    workspace = tmp_path / "workspace"
    baseline = capture_run_baseline(sessions, client, minio_bucket)
    transcript = SafeEventTranscript()
    storage = MinioCollectorSourceStorage(client, minio_bucket, workspace, 10 * 1024 * 1024)
    collector = CollectorEngine(
        CollectorPersistence(sessions),
        FixtureFeed(candidates),
        _CopyingDownloader(source),
        FfprobeSourceValidator(workspace, 10 * 1024 * 1024),
        storage,
        limits=CollectorLimits(
            max_target=3,
            max_advances=2,
            max_run_bytes=30 * 1024 * 1024,
            cooldown_seconds=0.001,
        ),
        recorder=transcript,
        sleep=lambda _seconds: None,
    )
    summary = collector.collect(account_id, CollectionTrigger.MANUAL, 3)
    assert summary.status == "completed"
    assert summary.source_committed_count == 3 and summary.confirmed_advances == 2
    with sessions() as session:
        assert len(session.scalars(select(InstagramReel)).all()) == 3
        assert session.get(InstagramCollectionRun, summary.run_id).source_committed_count == 3
    reuse = workspace / "temporary" / "reuse.part"
    reuse.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, reuse)
    identical = storage.publish(reuse, "instagram-sources/IT_STAGE3B_ONE.mp4")
    assert identical.created_by_attempt is False
    content = bytearray(reuse.read_bytes())
    content[0] ^= 1
    reuse.write_bytes(content)
    with pytest.raises(CollectorRuntimeError) as conflict:
        storage.publish(reuse, "instagram-sources/IT_STAGE3B_ONE.mp4")
    assert conflict.value.code is RuntimeReasonCode.STORAGE_OBJECT_CONFLICT
    storage.cleanup_temporary(reuse)
    assert summary.run_id is not None
    verification = CollectorPostRunVerifier(sessions, client, minio_bucket).verify(
        summary.run_id,
        baseline=baseline,
        transcript=transcript.events,
        workspace_root=workspace,
    )
    assert verification.verified


def _integration_configuration() -> tuple[str, str, str, str, str] | None:
    values = tuple(
        os.environ.get(key)
        for key in (
            "COLLECTOR_STAGE3B_IT_DATABASE_URL",
            "COLLECTOR_STAGE3B_IT_MINIO_ENDPOINT",
            "COLLECTOR_STAGE3B_IT_MINIO_ACCESS_KEY",
            "COLLECTOR_STAGE3B_IT_MINIO_SECRET_KEY",
            "COLLECTOR_STAGE3B_IT_MINIO_BUCKET",
        )
    )
    if not all(isinstance(value, str) and value for value in values):
        return None
    return values  # type: ignore[return-value]


class _CopyingDownloader:
    def __init__(self, source: Path) -> None:
        self._source = source

    def download(self, candidate: ReelCandidate, temporary_path: Path) -> None:
        del candidate
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._source, temporary_path)


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
