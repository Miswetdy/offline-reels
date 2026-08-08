"""Disposable Linux-container fixture for the real Collector composition.

This command is deliberately not a live runner: it creates local synthetic
MP4 files, uses the deterministic FeedPort and touches only PostgreSQL/MinIO.
"""

import argparse
import hashlib
import json
import os
import signal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.settings import Settings
from app.db.models.instagram import InstagramCollectionRun, InstagramNormalizationJob, InstagramReel
from app.db.models.video import Video
from app.db.session import create_session_factory
from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.fixtures import (
    FixtureFeed,
    FixtureRollbackFailingPersistence,
    SyntheticMp4Downloader,
)
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.collector.runtime.minio_client import create_collector_minio_client
from app.instagram.collector.runtime.minio_storage import MinioCollectorSourceStorage
from app.instagram.collector.runtime.profile_lock import ProfileLock, profile_path
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings
from app.instagram.collector.runtime.validator import FfprobeSourceValidator
from app.instagram.collector.runtime.workspace import attempt_workspace, cleanup_attempt_workspace
from app.instagram.collector.service import CollectorEngine, CollectorLimits
from app.instagram.contracts import AccountStatus, CollectionTrigger

FIXTURE_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000003c02")
FIXTURES = tuple(
    ReelCandidate(
        f"STAGE3C2_{number:03d}",
        f"https://www.instagram.com/reel/STAGE3C2_{number:03d}/",
    )
    for number in range(1, 4)
)
SCENARIOS = ("happy", "db-commit-failure", "cancel-after-first")


class _Transcript:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record(self, position: int, event: str) -> None:
        self.events.append({"position": position, "event": event})


class _CountingFixtureFeed(FixtureFeed):
    def __init__(self, candidates: list[ReelCandidate]) -> None:
        super().__init__(candidates)
        self.advance_calls = 0

    def advance(self) -> None:
        self.advance_calls += 1
        super().advance()


class _CancelAfterFirstDownloader(SyntheticMp4Downloader):
    def __init__(self) -> None:
        super().__init__()
        self._calls = 0

    def download(self, candidate: ReelCandidate, temporary_path: Path) -> None:
        self._calls += 1
        if self._calls > 1:
            raise KeyboardInterrupt
        super().download(candidate, temporary_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Network-isolated Collector container fixture.")
    parser.add_argument("--target", type=int, choices=(3,), default=3)
    parser.add_argument("--scenario", choices=SCENARIOS, default="happy")
    parser.add_argument("--account-id", type=UUID, default=FIXTURE_ACCOUNT_ID)
    arguments = parser.parse_args(argv)
    _install_signal_cancellation()
    try:
        payload, exit_code = run_fixture(arguments.target, arguments.scenario, arguments.account_id)
    except KeyboardInterrupt:
        # Engine normally turns this into a durable cancelled run. This branch
        # only protects an interrupt before a run has been created.
        payload, exit_code = {"phase": "stage-3c2-fixture", "status": "cancelled"}, 130
    except Exception:
        payload, exit_code = {"phase": "stage-3c2-fixture", "status": "failed"}, 1
    print(json.dumps(payload, sort_keys=True))
    return exit_code


def run_fixture(target: int, scenario: str, account_id: UUID) -> tuple[dict[str, object], int]:
    """Run the production persistence/storage/ffprobe path without a browser."""

    _require_fixture_network_contract()
    runtime = CollectorRuntimeSettings.from_environment()
    runtime.require_live(repository_root=Path("/app"))
    assert runtime.profile_root is not None
    assert runtime.workspace_root is not None
    settings = Settings()
    sessions = create_session_factory(settings)
    persistence = CollectorPersistence(sessions)
    client = create_collector_minio_client(settings)
    persistence.ensure_account(account_id)
    if persistence.account_status(account_id) is AccountStatus.DISCONNECTED:
        persistence.set_account_status(account_id, AccountStatus.CONNECTING)
    if persistence.account_status(account_id) is AccountStatus.CONNECTING:
        persistence.set_account_status(account_id, AccountStatus.CONNECTED)

    # A repeat smoke does not create a second run, second normalization job or
    # second object. It is a read-only idempotence proof.
    if scenario == "happy" and persistence.account_durable_count(account_id) >= target:
        return _verify_noop(sessions, client, settings.minio_bucket, account_id, target), 0

    run_token = uuid4()
    workspace = attempt_workspace(runtime.workspace_root, run_token)
    try:
        with ProfileLock(profile_path(runtime.profile_root, account_id)):
            feed = _CountingFixtureFeed(list(FIXTURES[:target]))
            recorder = _Transcript()
            persistence_port = (
                FixtureRollbackFailingPersistence(sessions)
                if scenario == "db-commit-failure"
                else persistence
            )
            downloader = (
                _CancelAfterFirstDownloader()
                if scenario == "cancel-after-first"
                else SyntheticMp4Downloader()
            )
            summary = CollectorEngine(
                persistence_port,
                feed,
                downloader,
                FfprobeSourceValidator(workspace, runtime.maximum_reel_bytes),
                MinioCollectorSourceStorage(
                    client, settings.minio_bucket, workspace, runtime.maximum_reel_bytes
                ),
                limits=CollectorLimits(
                    max_target=target,
                    max_advances=target - 1,
                    max_transition_operations=target - 1,
                    max_scroll_actions=(target - 1) * 2,
                    max_observations=target,
                    max_run_bytes=runtime.maximum_run_bytes,
                    cooldown_seconds=runtime.cooldown_seconds,
                    deadline_seconds=runtime.operator_deadline_seconds,
                ),
                recorder=recorder,
            ).collect(account_id, CollectionTrigger.MANUAL, target)
            payload = _summary_payload(summary, recorder.events, feed.advance_calls)
            if scenario == "happy":
                payload["verification"] = _verify_completed(
                    sessions,
                    client,
                    settings.minio_bucket,
                    account_id,
                    target,
                    recorder.events,
                    feed,
                )
                return payload, 0 if payload["verification"]["verified"] else 1
            if scenario == "db-commit-failure":
                payload["verification"] = _verify_rollback(client, settings.minio_bucket)
                return payload, 0 if payload["verification"]["verified"] else 1
            payload["verification"] = _verify_cancelled(sessions, account_id)
            return payload, 0 if payload["verification"]["verified"] else 1
    finally:
        cleanup_attempt_workspace(runtime.workspace_root, workspace)
        sessions.kw["bind"].dispose()


def _summary_payload(
    summary, events: list[dict[str, object]], advance_calls: int
) -> dict[str, object]:
    return {
        "phase": "stage-3c2-fixture",
        "status": summary.status,
        "target_count": summary.target_count,
        "source_committed_count": summary.source_committed_count,
        "already_available_count": summary.already_available_count,
        "failed_count": summary.failed_count,
        "confirmed_advances": summary.confirmed_advances,
        "stop_reason_code": summary.stop_reason_code,
        "advance_calls": advance_calls,
        "events": events,
    }


def _verify_completed(
    sessions, client, bucket: str, account_id, target: int, events, feed
) -> dict[str, object]:
    with sessions() as session:
        reels = session.scalars(select(InstagramReel).order_by(InstagramReel.shortcode)).all()
        pending = int(
            session.scalar(
                select(func.count()).select_from(InstagramNormalizationJob).where(
                    InstagramNormalizationJob.status == "pending"
                )
            )
            or 0
        )
        videos = int(session.scalar(select(func.count()).select_from(Video)) or 0)
    objects = list(client.list_objects(bucket, prefix="instagram-sources/", recursive=True))
    object_names = {item.object_name for item in objects}
    expected = {f"instagram-sources/{candidate.shortcode}.mp4" for candidate in FIXTURES[:target]}
    expected_events = ("detect", "pause", "download", "validation", "publication", "db_commit")
    per_position = {
        position: [event["event"] for event in events if event["position"] == position]
        for position in range(1, target + 1)
    }
    valid = (
        len(reels) == target
        and all(reel.pipeline_status == "source_ready" and reel.video_id is None for reel in reels)
        and pending == target
        and videos == 0
        and object_names == expected
        and all(
            item.size == reel.source_byte_size
            and _remote_sha256(client, bucket, item.object_name) == reel.source_sha256
            for item in objects
            for reel in reels
            if item.object_name == reel.source_object_key
        )
        and all(
            not any(
                marker in item.object_name for marker in (".part", ".ytdl", "staging", "temporary")
            )
            for item in objects
        )
        and all(
            all(name in per_position[position] for name in expected_events)
            for position in per_position
        )
        and feed.advance_calls == target - 1
        and "advance" not in per_position[target]
    )
    return {"verified": bool(valid), "object_count": len(objects), "pending_jobs": pending}


def _verify_noop(sessions, client, bucket: str, account_id, target: int) -> dict[str, object]:
    verification = _verify_completed(
        sessions, client, bucket, account_id, target, [], _NoScrollFeed()
    )
    # The event proof belongs to the original run. A no-op must only prove durable state.
    verification["verified"] = bool(
        verification["object_count"] == target and verification["pending_jobs"] == target
    )
    return {
        "phase": "stage-3c2-fixture",
        "status": "already_satisfied",
        "verification": verification,
    }


class _NoScrollFeed:
    advance_calls = 2


def _remote_sha256(client, bucket: str, object_name: str) -> str:
    response = client.get_object(bucket, object_name)
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    finally:
        response.close()
        response.release_conn()
    return digest.hexdigest()


def _verify_rollback(client, bucket: str) -> dict[str, object]:
    objects = list(client.list_objects(bucket, prefix="instagram-sources/", recursive=True))
    return {"verified": not objects, "object_count": len(objects)}


def _verify_cancelled(sessions, account_id) -> dict[str, object]:
    with sessions() as session:
        durable = int(
            session.scalar(
                select(func.count())
                .select_from(InstagramReel)
                .where(InstagramReel.pipeline_status == "source_ready")
            )
            or 0
        )
        cancelled = int(
            session.scalar(
                select(func.count())
                .select_from(InstagramCollectionRun)
                .where(
                    InstagramCollectionRun.account_id == account_id,
                    InstagramCollectionRun.status == "cancelled",
                    InstagramCollectionRun.stop_reason_code == "CANCELLED_BY_USER",
                )
            )
            or 0
        )
    return {
        "verified": durable == 1 and cancelled == 1,
        "durable_sources": durable,
        "cancelled_runs": cancelled,
        "account_id": str(account_id),
    }


def _require_fixture_network_contract() -> None:
    """Fixture mode permits only Compose-local DB/Object storage endpoints."""

    if os.environ.get("COLLECTOR_FIXTURE_NETWORK", "blocked") != "blocked":
        raise RuntimeError("fixture network guard is required")
    if "instagram.com" in os.environ.get("DATABASE_URL", "").lower():
        raise RuntimeError("invalid fixture database endpoint")
    if "instagram.com" in os.environ.get("MINIO_ENDPOINT", "").lower():
        raise RuntimeError("invalid fixture object endpoint")


def _install_signal_cancellation() -> None:
    def cancel(_signum, _frame) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)


if __name__ == "__main__":
    raise SystemExit(main())
