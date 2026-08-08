"""Explicit Stage 3C.1 continuation operator; never imported by FastAPI."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.core.settings import Settings
from app.db.models.instagram import (
    InstagramCollectionRunItem,
    InstagramNormalizationJob,
    InstagramReel,
)
from app.db.models.video import Video
from app.db.session import create_session_factory
from app.instagram.collector.persistence import CollectorPersistence, DurableReelSnapshot
from app.instagram.collector.runtime.browser_feed import PlaywrightReelsFeed
from app.instagram.collector.runtime.downloader import FreshSessionFirstYtDlpDownloader
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.factory import build_runtime_adapters
from app.instagram.collector.runtime.minio_client import create_collector_minio_client
from app.instagram.collector.runtime.operator import SafeEventTranscript
from app.instagram.collector.runtime.operator_state import load_or_create_account_id
from app.instagram.collector.runtime.settings import MEBIBYTE, CollectorRuntimeSettings
from app.instagram.collector.runtime.verification import (
    _is_temporary_name,
    _snapshot_object,
    _snapshot_objects,
    validate_stage3c1_transcript,
)
from app.instagram.collector.service import CollectorEngine, CollectorLimits, CollectorSummary
from app.instagram.contracts import AccountStatus, CollectionTrigger

STAGE_3C1_DESIRED_TOTAL = 10
STAGE_3C1_INITIAL_MINIMUM = 3
STAGE_3C1_MAX_NEW_BYTES = 700 * MEBIBYTE
STAGE_3C1_MAX_OBSERVATIONS = 30
STAGE_3C1_MAX_TRANSITIONS = 29
STAGE_3C1_MAX_WHEELS = 58


@dataclass(frozen=True)
class Stage3C1Plan:
    account_id: UUID
    initial_durable_count: int
    desired_total: int
    remaining: int
    baseline: tuple[DurableReelSnapshot, ...]


@dataclass(frozen=True)
class Stage3C1Verification:
    verified: bool
    final_durable_count: int
    reason_code: str | None


def prepare_stage3c1(
    persistence: CollectorPersistence,
    account_id: UUID,
    minio_client,
    bucket: str,
    desired_total: int,
) -> Stage3C1Plan:
    """Read-only continuation preflight. It deliberately runs before Chromium."""

    if desired_total != STAGE_3C1_DESIRED_TOTAL:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    initial = persistence.account_durable_count(account_id)
    baseline = persistence.account_durable_baseline(account_id)
    if initial != len(baseline) or initial < STAGE_3C1_INITIAL_MINIMUM or initial > desired_total:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    for item in baseline:
        try:
            remote = _snapshot_object(minio_client, bucket, item.object_key)
        except Exception as error:
            raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED) from error
        if (
            remote.byte_size != item.byte_size
            or remote.sha256 != item.sha256
            or remote.content_type != "video/mp4"
        ):
            raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    return Stage3C1Plan(account_id, initial, desired_total, desired_total - initial, baseline)


def run_stage3c1(
    *,
    runtime: CollectorRuntimeSettings,
    app_settings: Settings,
    repository_root: Path,
    desired_total: int,
    confirm: Callable[[], bool],
    wait_ready: Callable[[float], bool],
) -> tuple[CollectorSummary | None, SafeEventTranscript, Stage3C1Plan, str | None]:
    runtime.require_live(repository_root=repository_root)
    if (
        runtime.headless
        or runtime.maximum_target_count < STAGE_3C1_DESIRED_TOTAL
        or runtime.maximum_reel_bytes != 100 * MEBIBYTE
        or runtime.transition_polling_seconds != 0.25
        or runtime.transition_timeout_seconds != 10.0
        or runtime.operator_deadline_seconds != 3600.0
    ):
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    sessions = create_session_factory(app_settings)
    persistence = CollectorPersistence(sessions)
    assert runtime.workspace_root is not None
    account_id = load_or_create_account_id(runtime.workspace_root)
    persistence.ensure_account(account_id)
    if persistence.active_run_exists(account_id):
        raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_RUN_EXISTS)
    minio_client = create_collector_minio_client(app_settings)
    plan = prepare_stage3c1(
        persistence, account_id, minio_client, app_settings.minio_bucket, desired_total
    )
    transcript = SafeEventTranscript()
    transcript.account_id = account_id
    transcript.baseline = None  # Stage 3C.1 stores only account-owned immutable metadata below.
    if plan.remaining == 0:
        verification = verify_stage3c1(
            persistence, sessions, minio_client, app_settings.minio_bucket, plan, None, []
        )
        transcript.verification = {
            "verified": verification.verified,
            "final_durable_count": verification.final_durable_count,
            "reason_code": verification.reason_code,
        }
        if not verification.verified:
            return None, transcript, plan, "POST_RUN_VERIFICATION_FAILED"
        return None, transcript, plan, None
    if persistence.account_status(account_id) is not AccountStatus.CONNECTED:
        persistence.set_account_status(account_id, AccountStatus.CONNECTING)
    feed: PlaywrightReelsFeed | None = None
    try:
        feed = PlaywrightReelsFeed.open(
            account_id, runtime, repository_root=repository_root, allow_login_bootstrap=True
        )
        if not wait_ready(runtime.operator_deadline_seconds):
            return None, transcript, plan, RuntimeReasonCode.OPERATOR_TIMEOUT.value
        feed.current()
        persistence.set_account_status(account_id, AccountStatus.CONNECTED)
        if not confirm():
            return None, transcript, plan, "USER_CANCELLED"
        adapters = build_runtime_adapters(
            runtime,
            repository_root=repository_root,
            minio_client=minio_client,
            minio_bucket=app_settings.minio_bucket,
        )
        downloader = FreshSessionFirstYtDlpDownloader(
            lambda: feed.cookie_context, maximum_bytes=runtime.maximum_reel_bytes
        )
        engine = CollectorEngine(
            persistence,
            feed,
            downloader,
            adapters.validator,
            adapters.source_storage,
            limits=CollectorLimits(
                max_target=STAGE_3C1_DESIRED_TOTAL,
                max_advances=STAGE_3C1_MAX_TRANSITIONS,
                max_transition_operations=STAGE_3C1_MAX_TRANSITIONS,
                max_scroll_actions=STAGE_3C1_MAX_WHEELS,
                max_observations=STAGE_3C1_MAX_OBSERVATIONS,
                max_run_bytes=STAGE_3C1_MAX_NEW_BYTES,
                cooldown_seconds=max(runtime.cooldown_seconds, 0.5),
                deadline_seconds=3600.0,
            ),
            recorder=transcript,
        )
        summary = engine.collect(
            account_id,
            CollectionTrigger.MANUAL,
            plan.remaining,
            desired_account_total=STAGE_3C1_DESIRED_TOTAL,
        )
        transcript.download_diagnostics = downloader.attempt_diagnostics
        transcript.transition_diagnostics = engine.transition_diagnostics
        if summary.status == "completed":
            verification = verify_stage3c1(
                persistence,
                sessions,
                minio_client,
                app_settings.minio_bucket,
                plan,
                summary,
                transcript.events,
            )
            transcript.verification = {
                "verified": verification.verified,
                "final_durable_count": verification.final_durable_count,
                "reason_code": verification.reason_code,
            }
            if not verification.verified:
                return summary, transcript, plan, "POST_RUN_VERIFICATION_FAILED"
        return summary, transcript, plan, summary.stop_reason_code
    finally:
        if feed is not None:
            try:
                feed.close()
            except Exception:
                pass


def safe_stage3c1_json(
    summary: CollectorSummary | None,
    transcript: SafeEventTranscript,
    plan: Stage3C1Plan,
    reason: str | None,
) -> str:
    payload: dict[str, object] = {
        "phase": "stage-3c1",
        "account_id": str(plan.account_id),
        "desired_total": plan.desired_total,
        "initial_durable_count": plan.initial_durable_count,
        "remaining": plan.remaining,
        "final_durable_count": (
            plan.desired_total
            if summary is not None and summary.status == "completed"
            else plan.initial_durable_count
        ),
        "immutable_baseline": [
            {
                "reel_id": str(item.reel_id),
                "object_key": item.object_key,
                "sha256": item.sha256,
                "byte_size": item.byte_size,
            }
            for item in plan.baseline
        ],
        "events": transcript.events,
        "stop_reason_code": reason,
    }
    if summary is not None:
        payload["summary"] = {
            key: str(value) if key == "run_id" and value else value
            for key, value in asdict(summary).items()
        }
    if transcript.download_diagnostics:
        payload["download_diagnostics"] = transcript.download_diagnostics
    if transcript.transition_diagnostics:
        payload["transition_diagnostics"] = transcript.transition_diagnostics
    if transcript.verification is not None:
        payload["verification"] = transcript.verification
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def verify_stage3c1(
    persistence: CollectorPersistence,
    sessions,
    minio_client,
    bucket: str,
    plan: Stage3C1Plan,
    summary: CollectorSummary | None,
    events: list[dict[str, object]],
) -> Stage3C1Verification:
    """Read-only durable-state verifier for a completed continuation or no-op."""

    final_count = persistence.account_durable_count(plan.account_id)
    snapshots = persistence.account_durable_baseline(plan.account_id)
    valid = final_count == STAGE_3C1_DESIRED_TOTAL == len(snapshots)
    original = {item.reel_id: item for item in plan.baseline}
    current = {item.reel_id: item for item in snapshots}
    valid = valid and all(current.get(key) == value for key, value in original.items())
    try:
        current_objects = {item.object_key for item in _snapshot_objects(minio_client, bucket)}
        expected_objects = {item.object_key for item in snapshots}
        valid = valid and current_objects == expected_objects
        valid = valid and all(not _is_temporary_name(key) for key in current_objects)
        for snapshot in snapshots:
            remote = _snapshot_object(minio_client, bucket, snapshot.object_key)
            valid = (
                valid
                and remote.byte_size == snapshot.byte_size
                and remote.sha256 == snapshot.sha256
                and remote.content_type == "video/mp4"
            )
    except Exception:
        valid = False
    with sessions() as session:
        reels = session.scalars(
            select(InstagramReel)
            .join(
                InstagramCollectionRunItem, InstagramCollectionRunItem.reel_id == InstagramReel.id
            )
            .where(InstagramCollectionRunItem.reel_id.in_([item.reel_id for item in snapshots]))
            .distinct()
        ).all()
        pending = session.execute(
            select(InstagramNormalizationJob.reel_id, func.count())
            .where(
                InstagramNormalizationJob.reel_id.in_([item.reel_id for item in snapshots]),
                InstagramNormalizationJob.status == "pending",
            )
            .group_by(InstagramNormalizationJob.reel_id)
        ).all()
        valid = (
            valid
            and len(reels) == STAGE_3C1_DESIRED_TOTAL
            and all(reel.video_id is None for reel in reels)
        )
        valid = (
            valid
            and len(pending) == STAGE_3C1_DESIRED_TOTAL
            and all(count == 1 for _reel_id, count in pending)
        )
        valid = valid and int(session.scalar(select(func.count()).select_from(Video)) or 0) == 0
    if summary is not None:
        valid = (
            valid
            and summary.status == "completed"
            and summary.target_count == plan.remaining
            and summary.source_committed_count == plan.remaining
            and summary.already_available_count == 0
            and summary.failed_count == 0
        )
        valid = valid and validate_stage3c1_transcript(
            events, status="completed", final_position=summary.observations
        )
    return Stage3C1Verification(
        bool(valid), final_count, None if valid else "POST_RUN_VERIFICATION_FAILED"
    )


def write_stage3c1_result(workspace_root: Path, payload: str) -> Path:
    data = json.loads(payload)
    run_id = (data.get("summary") or {}).get("run_id") if isinstance(data, dict) else None
    destination = (
        workspace_root.resolve(strict=False) / "results" / f"stage-3c1-{run_id or 'no-run'}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(payload + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination
