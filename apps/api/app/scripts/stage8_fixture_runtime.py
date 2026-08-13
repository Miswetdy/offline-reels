"""Disposable synthetic services for the Stage 8 local-reserve fixture.

This module never contacts Instagram and never opens a browser profile.  It is
only started by ``deploy/docker-compose.stage8-fixture.yml`` with a fresh
PostgreSQL/MinIO volume pair.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.management import hash_secret
from app.core.settings import get_settings
from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    InstagramLoginSession,
    InstagramNormalizationJob,
    InstagramReel,
    ManagementPairingChallenge,
)
from app.db.models.video import Video
from app.db.session import create_session_factory
from app.instagram.contracts import AccountStatus, LoginSessionStatus
from app.storage.minio import MinioVideoStorage


@lru_cache
def fixture_mp4() -> bytes:
    """Produce a tiny decodable H.264/yuv420p MP4 without external media."""
    with tempfile.TemporaryDirectory(prefix="stage8-fixture-") as directory:
        output = Path(directory) / "fixture.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=64x64:r=24", "-frames:v", "6", "-an", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
            ],
            check=True,
            timeout=30,
        )
        return output.read_bytes()


@lru_cache
def sessions():
    return create_session_factory(get_settings())


def bootstrap() -> None:
    """Create just one disconnected account and pairing challenge, no catalog."""
    secret = os.environ["STAGE8_FIXTURE_PAIRING_SECRET"]
    now = datetime.now(UTC)
    with sessions().begin() as db:
        existing = db.scalar(
            select(ManagementPairingChallenge)
            .where(ManagementPairingChallenge.secret_hash == hash_secret(secret))
            .with_for_update()
        )
        if existing is not None:
            if existing.consumed_at is None and existing.expires_at <= now:
                existing.expires_at = now + timedelta(minutes=20)
            return
        account = InstagramAccount(status=AccountStatus.DISCONNECTED.value)
        db.add(account)
        db.flush()
        db.add(
            ManagementPairingChallenge(
                account_id=account.id,
                secret_hash=hash_secret(secret),
                expires_at=now + timedelta(minutes=20),
            )
        )


def gateway() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/connect/{session_id}", response_class=RedirectResponse)
    def connect(session_id: str) -> RedirectResponse:
        with sessions().begin() as db:
            account = db.scalar(select(InstagramAccount).limit(1))
            if account is not None:
                account.status = AccountStatus.CONNECTED.value
                account.reason_code = None
                account.reauth_required_at = None
                account.last_connected_at = datetime.now(UTC)
            login = db.get(InstagramLoginSession, UUID(session_id), with_for_update=True)
            if login is not None:
                login.status = LoginSessionStatus.COMPLETED.value
                login.closed_at = datetime.now(UTC)
        return RedirectResponse(url="/#", status_code=303, headers={"Cache-Control": "no-store"})

    return app


def collector() -> None:
    """Turn exactly one queued bounded management run into source-ready records."""
    delay = float(os.environ.get("STAGE8_FIXTURE_COLLECTOR_DELAY", "0.4"))
    while True:
        with sessions().begin() as db:
            run = db.scalar(
                select(InstagramCollectionRun)
                .where(InstagramCollectionRun.status == "queued")
                .with_for_update(skip_locked=True)
            )
            if run is not None:
                run.status = "running"
            run_id = run.id if run is not None else None
        if run_id is None:
            time.sleep(0.15)
            continue
        time.sleep(delay)
        with sessions().begin() as db:
            run = db.get(InstagramCollectionRun, run_id, with_for_update=True)
            if run is None or run.cancel_requested_at is not None:
                if run is not None:
                    run.status = "cancelled"
                continue
            run.source_committed_count = run.target_count
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            for _ in range(run.target_count):
                identifier = uuid4().hex
                reel = InstagramReel(
                    shortcode=f"fixture-{identifier}",
                    canonical_url=f"https://fixture.invalid/reel/{identifier}",
                    pipeline_status="source_ready",
                    source_object_key=f"synthetic-source/{identifier}",
                    source_sha256="a" * 64,
                    source_byte_size=1,
                )
                db.add(reel)
                db.flush()
                db.add(
                    InstagramNormalizationJob(
                        reel_id=reel.id, status="pending", attempt_count=0
                    )
                )


def normalizer() -> None:
    """Safe synthetic normalizer: produces valid fixture MP4 ready catalog rows."""
    storage = MinioVideoStorage(get_settings())
    storage.ensure_bucket()
    video_bytes = fixture_mp4()
    while True:
        with sessions().begin() as db:
            job = db.scalar(
                select(InstagramNormalizationJob)
                .where(InstagramNormalizationJob.status == "pending")
                .with_for_update(skip_locked=True)
            )
            if job is not None:
                job.status = "running"
                job.attempt_count += 1
            job_id = job.id if job is not None else None
        if job_id is None:
            time.sleep(0.15)
            continue
        key = f"synthetic-ready/{uuid4().hex}.mp4"
        storage._client.put_object(
            storage._bucket,
            key,
            io.BytesIO(video_bytes),
            len(video_bytes),
            content_type="video/mp4",
        )
        with sessions().begin() as db:
            current = db.get(InstagramNormalizationJob, job_id, with_for_update=True)
            if current is None:
                continue
            video = Video(
                title="Fixture Reel",
                object_key=key,
                content_type="video/mp4",
                byte_size=len(video_bytes),
            )
            db.add(video)
            db.flush()
            reel = db.get(InstagramReel, current.reel_id, with_for_update=True)
            if reel is not None:
                reel.pipeline_status = "ready"
                reel.video_id = video.id
                reel.ready_at = datetime.now(UTC)
            current.status = "completed"
            current.completed_at = datetime.now(UTC)


if __name__ == "__main__":
    mode = os.environ["STAGE8_FIXTURE_MODE"]
    if mode == "bootstrap":
        bootstrap()
    elif mode == "collector":
        collector()
    elif mode == "normalizer":
        normalizer()
    else:
        raise SystemExit("Unknown Stage 8 fixture mode")
