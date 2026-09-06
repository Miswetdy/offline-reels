"""Explicit, Windows-hosted Stage 3B operator composition.  No import side effects."""

import json
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from app.core.settings import Settings
from app.db.session import create_session_factory
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.collector.runtime.browser_feed import PlaywrightReelsFeed
from app.instagram.collector.runtime.downloader import FreshSessionFirstYtDlpDownloader
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.factory import build_runtime_adapters
from app.instagram.collector.runtime.minio_client import create_collector_minio_client
from app.instagram.collector.runtime.operator_state import load_or_create_account_id
from app.instagram.collector.runtime.settings import MEBIBYTE, CollectorRuntimeSettings
from app.instagram.collector.runtime.verification import (
    CollectorPostRunVerifier,
    RunBaseline,
    capture_run_baseline,
)
from app.instagram.collector.service import CollectorEngine, CollectorLimits, CollectorSummary
from app.instagram.contracts import AccountStatus, CollectionTrigger

STAGE_3B_TARGET = 3
STAGE_3B_MAX_BYTES = 300 * MEBIBYTE


class SafeEventTranscript:
    """Bounded, non-sensitive event names used by the operator and verifier."""

    _allowed = frozenset(
        {
            "detect",
            "pause",
            "download",
            "validation",
            "publish",
            "db_commit",
            "cooldown",
            "feed_source_advance",
            "advance",
            "advance_retry",
            "transition_confirmed",
            "duplicate_skipped",
        }
    )

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.verification: dict[str, object] | None = None
        self.baseline: RunBaseline | None = None
        self.account_id: UUID | None = None
        self.feed_diagnostics: dict[str, object] | None = None
        self.download_diagnostics: list[dict[str, object]] = []
        self.transition_diagnostics: list[dict[str, object]] = []

    def record(self, position: int, event: str) -> None:
        if event == "publication":
            event = "publish"
        if event in self._allowed and len(self.events) < 256:
            self.events.append({"position": position, "event": event})


def run_stage_3b(
    *,
    runtime: CollectorRuntimeSettings,
    app_settings: Settings,
    repository_root: Path,
    confirm: Callable[[], bool],
    wait_ready: Callable[[float], bool],
    account_id: UUID | None = None,
    existing_feed: PlaywrightReelsFeed | None = None,
) -> tuple[CollectorSummary | None, SafeEventTranscript, str | None]:
    """Run exactly three Reels after explicit human readiness and confirmation."""

    runtime.require_live(repository_root=repository_root)
    if runtime.headless or runtime.maximum_target_count < STAGE_3B_TARGET:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    sessions = create_session_factory(app_settings)
    persistence = CollectorPersistence(sessions)
    assert runtime.workspace_root is not None
    account_id = account_id or load_or_create_account_id(runtime.workspace_root)
    persistence.ensure_account(account_id)
    # The management API writes a bounded command as ``queued``. Claim it
    # before opening Chromium so an operator-launched Stage 3B process updates
    # the exact run the PWA is polling. With no queued command this preserves
    # the existing explicit Stage 3B behaviour of creating its own run.
    claim = getattr(persistence, "claim_queued_run", lambda _account_id: None)(account_id)
    if claim is not None and claim.target_count != STAGE_3B_TARGET:
        persistence.fail_run(claim.id, "UNSUPPORTED_TARGET")
        return None, SafeEventTranscript(), RuntimeReasonCode.COLLECTOR_DISABLED.value
    if claim is None and persistence.active_run_exists(account_id):
        raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_RUN_EXISTS)
    current_status = persistence.account_status(account_id)
    if current_status is not AccountStatus.CONNECTED:
        persistence.set_account_status(account_id, AccountStatus.CONNECTING)

    transcript = SafeEventTranscript()
    transcript.account_id = account_id
    feed: PlaywrightReelsFeed | None = existing_feed
    try:
        if feed is None:
            feed = PlaywrightReelsFeed.open(
                account_id,
                runtime,
                repository_root=repository_root,
                allow_login_bootstrap=True,
            )
        if not wait_ready(runtime.operator_deadline_seconds):
            _fail_claimed_run(persistence, claim, RuntimeReasonCode.OPERATOR_TIMEOUT.value)
            return None, transcript, RuntimeReasonCode.OPERATOR_TIMEOUT.value
        # current() rechecks auth/checkpoint and validates a central Reel.
        feed.current()
        persistence.set_account_status(account_id, AccountStatus.CONNECTED)
        if not confirm():
            if claim is not None:
                persistence.cancel_run(claim.id, "USER_CANCELLED")
            return None, transcript, "USER_CANCELLED"
        minio_client = create_collector_minio_client(app_settings)
        transcript.baseline = capture_run_baseline(
            sessions,
            minio_client,
            app_settings.minio_bucket,
        )
        adapters = build_runtime_adapters(
            runtime,
            repository_root=repository_root,
            minio_client=minio_client,
            minio_bucket=app_settings.minio_bucket,
        )
        downloader = FreshSessionFirstYtDlpDownloader(
            lambda: feed.cookie_context,
            maximum_bytes=runtime.maximum_reel_bytes,
        )
        engine = CollectorEngine(
            persistence,
            feed,
            downloader,
            adapters.validator,
            adapters.source_storage,
            limits=CollectorLimits(
                max_target=STAGE_3B_TARGET,
                max_advances=STAGE_3B_TARGET - 1,
                max_transition_operations=STAGE_3B_TARGET - 1,
                max_scroll_actions=4,
                max_run_bytes=min(runtime.maximum_run_bytes, STAGE_3B_MAX_BYTES),
                cooldown_seconds=max(runtime.cooldown_seconds, 0.5),
                deadline_seconds=runtime.operator_deadline_seconds,
            ),
            recorder=transcript,
        )
        summary = engine.collect(
            account_id,
            CollectionTrigger.MANUAL,
            STAGE_3B_TARGET,
            claimed_run_id=claim.id if claim is not None else None,
        )
        transcript.download_diagnostics = downloader.attempt_diagnostics
        transcript.transition_diagnostics = engine.transition_diagnostics
        if summary.stop_reason_code is not None:
            try:
                _set_safe_account_state(
                    persistence,
                    account_id,
                    RuntimeReasonCode(summary.stop_reason_code),
                )
            except ValueError:
                pass
        if summary.status == "completed" and summary.run_id is not None:
            verification = CollectorPostRunVerifier(
                sessions,
                minio_client,
                app_settings.minio_bucket,
            ).verify(
                summary.run_id,
                baseline=transcript.baseline,
                transcript=transcript.events,
                workspace_root=runtime.workspace_root,
            )
            transcript.verification = {
                "verified": verification.verified,
                "video_count_unchanged": verification.video_count_unchanged,
                "reason_code": verification.reason_code,
            }
            if not verification.verified:
                return (
                    summary,
                    transcript,
                    RuntimeReasonCode.POST_RUN_VERIFICATION_FAILED.value,
                )
        return summary, transcript, None
    except CollectorRuntimeError as error:
        if feed is not None:
            transcript.feed_diagnostics = feed.diagnostics
        _fail_claimed_run(persistence, claim, error.code.value)
        _set_safe_account_state(persistence, account_id, error.code)
        return None, transcript, error.code.value
    except Exception:
        # A control-plane run must never remain active when setup failed before
        # CollectorEngine can record its own terminal state.
        _fail_claimed_run(persistence, claim, "COLLECTOR_FAILED")
        raise
    finally:
        try:
            if feed is not None:
                feed.close()
        except Exception:
            pass


def _fail_claimed_run(
    persistence: CollectorPersistence,
    claim: object | None,
    reason_code: str,
) -> None:
    if claim is not None:
        persistence.fail_run(claim.id, reason_code)


def _set_safe_account_state(
    persistence: CollectorPersistence, account_id: UUID, code: RuntimeReasonCode
) -> None:
    try:
        if code in {
            RuntimeReasonCode.AUTH_REQUIRED,
            RuntimeReasonCode.SESSION_COOKIE_MISSING,
            RuntimeReasonCode.DIRECT_DOWNLOAD_AUTH_REQUIRED,
        }:
            persistence.set_account_status(account_id, AccountStatus.REAUTH_REQUIRED, code.value)
        elif code is RuntimeReasonCode.CHECKPOINT_REQUIRED:
            persistence.set_account_status(account_id, AccountStatus.REAUTH_REQUIRED, code.value)
        elif code is RuntimeReasonCode.TEMPORARILY_LIMITED:
            persistence.set_account_status(
                account_id,
                AccountStatus.TEMPORARILY_LIMITED,
                code.value,
            )
    except Exception:
        pass


def wait_for_operator_enter(timeout_seconds: float) -> bool:
    """Windows console prompt with a deadline; never asks for credentials."""

    if sys.platform != "win32":
        return False
    import msvcrt

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if msvcrt.kbhit() and msvcrt.getwch() in {"\r", "\n"}:
            return True
        time.sleep(0.05)
    return False


def safe_summary_json(
    summary: CollectorSummary | None,
    transcript: SafeEventTranscript,
    reason: str | None,
) -> str:
    effective_reason = reason
    if effective_reason is None and summary is not None and summary.stop_reason_code is not None:
        effective_reason = summary.stop_reason_code
    payload: dict[str, object] = {
        "phase": "stage-3b",
        "events": transcript.events,
        "stop_reason_code": effective_reason,
    }
    if transcript.baseline is not None:
        payload["baseline"] = transcript.baseline.to_safe_dict()
    if transcript.feed_diagnostics is not None:
        payload["feed_diagnostics"] = transcript.feed_diagnostics
    if transcript.download_diagnostics:
        payload["download_diagnostics"] = transcript.download_diagnostics
    if transcript.transition_diagnostics:
        payload["transition_diagnostics"] = transcript.transition_diagnostics
    if transcript.verification is not None:
        payload["verification"] = transcript.verification
    if summary is not None:
        payload["summary"] = {
            key: str(value) if key == "run_id" and value is not None else value
            for key, value in asdict(summary).items()
        }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def write_safe_result(workspace_root: Path, summary_json: str) -> Path:
    """Write only the already-redacted result outside the browser profile."""

    payload = json.loads(summary_json)
    run_id = (payload.get("summary") or {}).get("run_id") if isinstance(payload, dict) else None
    suffix = run_id if isinstance(run_id, str) else "no-run"
    destination = workspace_root.resolve(strict=False) / "results" / f"stage-3b-{suffix}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(summary_json + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination
