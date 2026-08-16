"""Disposable synthetic Stage 9 Collector/normalizer fixture.

This process has no Instagram, browser profile, cookies, or live media input.
It is only used by the isolated ``stage9`` Compose project.
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
    InstagramCollectionRunItem,
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
def fixture_mp4(seconds: int) -> bytes:
    """Generate tiny decodable fixture MP4s with explicit, differing durations."""
    with tempfile.TemporaryDirectory(prefix="stage9-fixture-") as directory:
        output = Path(directory) / f"fixture-{seconds}s.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=64x64:r=24", "-t", str(seconds), "-an", "-c:v", "libx264",
                "-profile:v", "baseline", "-level:v", "3.0", "-preset", "ultrafast",
                "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
            ],
            check=True,
            timeout=30,
        )
        return output.read_bytes()


@lru_cache
def sessions():
    return create_session_factory(get_settings())


def bootstrap() -> None:
    secrets = (
        os.environ["STAGE9_FIXTURE_PAIRING_SECRET"],
        os.environ["STAGE9_FIXTURE_SECOND_PAIRING_SECRET"],
    )
    now = datetime.now(UTC)
    with sessions().begin() as db:
        for secret in secrets:
            existing = db.scalar(
                select(ManagementPairingChallenge)
                .where(ManagementPairingChallenge.secret_hash == hash_secret(secret))
                .with_for_update()
            )
            if existing is not None:
                continue
            account = InstagramAccount(status=AccountStatus.DISCONNECTED.value)
            db.add(account)
            db.flush()
            db.add(ManagementPairingChallenge(
                account_id=account.id,
                secret_hash=hash_secret(secret),
                expires_at=now + timedelta(minutes=20),
            ))


def gateway() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/connect/{session_id}", response_class=RedirectResponse)
    def connect(session_id: str) -> RedirectResponse:
        with sessions().begin() as db:
            login = db.get(InstagramLoginSession, UUID(session_id), with_for_update=True)
            if login is not None:
                # A pairing secret selects an account.  The fixture gateway
                # must connect that exact account rather than whichever row
                # happens to be first in PostgreSQL.
                account = db.get(InstagramAccount, login.account_id, with_for_update=True)
                if account is not None:
                    account.status = AccountStatus.CONNECTED.value
                    account.last_connected_at = datetime.now(UTC)
                login.status = LoginSessionStatus.COMPLETED.value
                login.closed_at = datetime.now(UTC)
        return RedirectResponse(url="/#", status_code=303, headers={"Cache-Control": "no-store"})

    return app


def collector() -> None:
    """Synthetic account-owned sources; every output is attached to its run."""
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
            time.sleep(0.1)
            continue
        with sessions().begin() as db:
            run = db.get(InstagramCollectionRun, run_id, with_for_update=True)
            if run is None or run.cancel_requested_at is not None:
                if run is not None:
                    run.status = "cancelled"
                continue
            for position in range(1, run.target_count + 1):
                identifier = uuid4().hex
                reel = InstagramReel(
                    shortcode=f"stage9-{identifier}",
                    canonical_url=f"https://fixture.invalid/reel/{identifier}",
                    pipeline_status="source_ready",
                    source_object_key=f"synthetic-source/{identifier}",
                    source_sha256="a" * 64,
                    source_byte_size=1,
                )
                db.add(reel)
                db.flush()
                db.add(InstagramCollectionRunItem(
                    run_id=run.id, reel_id=reel.id, position=position,
                    outcome="source_committed", download_auth_mode="session_first",
                ))
                # The Stage 9 fixture deliberately exposes the same canonical
                # Reel to its second synthetic account. Production ownership
                # remains account-scoped; this proves one account's view does
                # not remove the global canonical media for another account.
                for other_account in db.scalars(
                    select(InstagramAccount.id).where(InstagramAccount.id != run.account_id)
                ):
                    mirror = InstagramCollectionRun(
                        account_id=other_account,
                        trigger="manual",
                        status="completed",
                        target_count=1,
                        source_committed_count=0, already_available_count=1,
                    )
                    db.add(mirror)
                    db.flush()
                    db.add(InstagramCollectionRunItem(
                        run_id=mirror.id, reel_id=reel.id, position=1,
                        outcome="already_available", download_auth_mode=None,
                    ))
                db.add(
                    InstagramNormalizationJob(reel_id=reel.id, status="pending", attempt_count=0)
                )
            run.source_committed_count = run.target_count
            run.status = "completed"
            run.completed_at = datetime.now(UTC)


def normalizer() -> None:
    storage = MinioVideoStorage(get_settings())
    storage.ensure_bucket()
    ordinal = 0
    while True:
        with sessions().begin() as db:
            job = db.scalar(
                select(InstagramNormalizationJob)
                .where(InstagramNormalizationJob.status == "pending")
                .with_for_update(skip_locked=True)
            )
            if job is not None:
                job.status, job.attempt_count = "running", job.attempt_count + 1
            job_id = job.id if job is not None else None
        if job_id is None:
            time.sleep(0.1)
            continue
        # First fixture media is short (<3 s); later items are normal duration.
        seconds = 2 if ordinal == 0 else 5
        ordinal += 1
        body = fixture_mp4(seconds)
        key = f"synthetic-ready/{uuid4().hex}-{seconds}s.mp4"
        storage._client.put_object(
            storage._bucket, key, io.BytesIO(body), len(body), content_type="video/mp4"
        )
        with sessions().begin() as db:
            current = db.get(InstagramNormalizationJob, job_id, with_for_update=True)
            if current is None:
                continue
            video = Video(
                title=f"Fixture {seconds}s Reel",
                object_key=key,
                content_type="video/mp4",
                byte_size=len(body),
                duration_ms=seconds * 1000,
            )
            db.add(video)
            db.flush()
            reel = db.get(InstagramReel, current.reel_id, with_for_update=True)
            if reel is not None:
                reel.pipeline_status = "ready"
                reel.video_id = video.id
                reel.ready_at = datetime.now(UTC)
            current.status, current.completed_at = "completed", datetime.now(UTC)


if __name__ == "__main__":
    mode = os.environ["STAGE9_FIXTURE_MODE"]
    if mode == "bootstrap":
        bootstrap()
    elif mode == "collector":
        collector()
    elif mode == "normalizer":
        normalizer()
    else:
        raise SystemExit("Unknown Stage 9 fixture mode")
