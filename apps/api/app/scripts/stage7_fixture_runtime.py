"""Disposable synthetic Stage 7 services; never contacts Instagram."""

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

FIXTURE_CATALOG_SEED_COUNT = 11


@lru_cache
def fixture_mp4() -> bytes:
    """Generate tiny decodable fixture media without contacting any service."""
    with tempfile.TemporaryDirectory(prefix="stage7-fixture-") as directory:
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
    """One engine per disposable fixture process, not one per polling pass."""
    return create_session_factory(get_settings())


def bootstrap() -> None:
    secret = os.environ["STAGE7_FIXTURE_PAIRING_SECRET"]
    secret_hash = hash_secret(secret)
    now = datetime.now(UTC)
    video_bytes = fixture_mp4()
    storage = MinioVideoStorage(get_settings())
    storage.ensure_bucket()
    with sessions().begin() as db:
        # Compose can recreate a dependent service while retaining this
        # fixture's disposable PostgreSQL volume. A prior successful bootstrap
        # is complete (the transaction below is atomic), so never duplicate
        # its operator code, account, or synthetic catalog on retry.
        existing = db.scalar(
            select(ManagementPairingChallenge)
            .where(ManagementPairingChallenge.secret_hash == secret_hash)
            .with_for_update()
        )
        if existing is not None:
            # Manual fixture acceptance can take longer than the intentionally
            # short pairing TTL. Renew only an unconsumed fixture challenge;
            # a consumed code remains permanently consumed even on restart.
            if existing.consumed_at is None and existing.expires_at <= now:
                existing.expires_at = now + timedelta(minutes=20)
            return
        account = InstagramAccount(status=AccountStatus.DISCONNECTED.value)
        db.add(account)
        db.flush()
        db.add(
            ManagementPairingChallenge(
                account_id=account.id,
                secret_hash=secret_hash,
                expires_at=now + timedelta(minutes=20),
            )
        )
        # Seed more than one catalog page across the later fixture runs.
        # These are only synthetic streamable objects; no external media or
        # Instagram data is involved.
        for position in range(FIXTURE_CATALOG_SEED_COUNT):
            key = f"fixture/seed-{position}.mp4"
            storage._client.put_object(
                storage._bucket,
                key,
                io.BytesIO(video_bytes),
                len(video_bytes),
                content_type="video/mp4",
            )
            db.add(
                Video(
                    title="Fixture Reel",
                    object_key=key,
                    content_type="video/mp4",
                    byte_size=len(video_bytes),
                )
            )


def gateway() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/connect/{_session_id}", response_class=RedirectResponse)
    def connect(_session_id: str) -> RedirectResponse:
        with sessions().begin() as db:
            account = db.scalar(select(InstagramAccount).limit(1))
            if account is not None:
                account.status = AccountStatus.CONNECTED.value
                account.reason_code = None
                account.reauth_required_at = None
                account.last_connected_at = datetime.now(UTC)
            login = db.get(InstagramLoginSession, UUID(_session_id), with_for_update=True)
            if login is not None:
                login.status = LoginSessionStatus.COMPLETED.value
                login.closed_at = datetime.now(UTC)
        # The fixture gateway deliberately has one safe return destination.
        # The explicit empty fragment prevents a launch-token fragment from
        # being retained across the redirect by the browser.
        return RedirectResponse(url="/#", status_code=303, headers={"Cache-Control": "no-store"})

    return app


def collector() -> None:
    delay = float(os.environ.get("STAGE7_FIXTURE_COLLECTOR_DELAY", "2"))
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
            time.sleep(0.2)
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
                    canonical_url=f"https://fixture.invalid/{identifier}",
                    pipeline_status="source_ready",
                    source_object_key=f"source/{identifier}",
                    source_sha256="a" * 64,
                    source_byte_size=13,
                )
                db.add(reel)
                db.flush()
                db.add(
                    InstagramNormalizationJob(reel_id=reel.id, status="pending", attempt_count=0)
                )


def normalizer() -> None:
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
            if job is None:
                pass
            else:
                job.status = "running"
                job.attempt_count += 1
        if job is None:
            time.sleep(0.2)
            continue
        time.sleep(0.15)
        identifier = uuid4().hex
        key = f"fixture/{identifier}.mp4"
        storage._client.put_object(
            storage._bucket,
            key,
            io.BytesIO(video_bytes),
            len(video_bytes),
            content_type="video/mp4",
        )
        with sessions().begin() as db:
            current = db.get(InstagramNormalizationJob, job.id, with_for_update=True)
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
    mode = os.environ["STAGE7_FIXTURE_MODE"]
    if mode == "bootstrap":
        bootstrap()
    elif mode == "collector":
        collector()
    elif mode == "normalizer":
        normalizer()
