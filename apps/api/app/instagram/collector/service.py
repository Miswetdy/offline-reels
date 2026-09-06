"""Sequential, side-effect-oriented Collector orchestration."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.instagram.collector.canonical import (
    InvalidReelCandidate,
    source_object_key,
    validate_candidate,
)
from app.instagram.collector.contracts import (
    HIT_TEST_DIAGNOSTIC_FLAGS,
    CollectorUnitOfWorkPort,
    DownloaderPort,
    EventRecorder,
    FeedPort,
    NullEventRecorder,
    ReelCandidate,
    ScrollTargetDiagnostics,
    SourceStoragePort,
    TransitionSamplingDiagnostics,
    ValidatorPort,
)
from app.instagram.contracts import CollectionTrigger, ReelPipelineStatus


@dataclass(frozen=True)
class CollectorLimits:
    max_target: int = 5
    max_advances: int = 10
    max_transition_operations: int | None = None
    max_scroll_actions: int | None = None
    max_run_bytes: int | None = None
    cooldown_seconds: float = 0.0
    deadline_seconds: float | None = None
    max_observations: int | None = None


@dataclass(frozen=True)
class CollectorSummary:
    run_id: UUID | None
    status: str
    target_count: int
    source_committed_count: int
    already_available_count: int
    failed_count: int
    confirmed_advances: int
    stop_reason_code: str | None
    observations: int = 0
    duplicate_skipped_count: int = 0


class CollectorEngine:
    def __init__(
        self,
        persistence: CollectorUnitOfWorkPort,
        feed: FeedPort,
        downloader: DownloaderPort,
        validator: ValidatorPort,
        storage: SourceStoragePort,
        *,
        limits: CollectorLimits = CollectorLimits(),
        recorder: EventRecorder | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._persistence = persistence
        self._feed = feed
        self._downloader = downloader
        self._validator = validator
        self._storage = storage
        self._limits = limits
        self._recorder = recorder or NullEventRecorder()
        self._clock = clock
        self._sleep = sleep
        self._transition_diagnostics: list[dict[str, object]] = []

    @property
    def transition_diagnostics(self) -> list[dict[str, object]]:
        """Bounded, aggregate-only transition data for the safe operator result."""

        return [dict(item) for item in self._transition_diagnostics]

    def collect(
        self,
        account_id: UUID,
        trigger: CollectionTrigger,
        target_count: int,
        *,
        desired_account_total: int | None = None,
        claimed_run_id: UUID | None = None,
    ) -> CollectorSummary:
        if target_count < 1 or target_count > self._limits.max_target:
            raise ValueError("Target is outside the fixture Collector limit.")
        if self._limits.max_run_bytes is not None and self._limits.max_run_bytes < 1:
            raise ValueError("Collector byte limit must be positive.")
        if self._limits.cooldown_seconds < 0:
            raise ValueError("Collector cooldown must not be negative.")
        if self._limits.max_transition_operations is not None and (
            self._limits.max_transition_operations < 1
        ):
            raise ValueError("Collector transition-operation limit must be positive.")
        if self._limits.max_scroll_actions is not None and self._limits.max_scroll_actions < 1:
            raise ValueError("Collector scroll-action limit must be positive.")
        if self._limits.deadline_seconds is not None and self._limits.deadline_seconds <= 0:
            raise ValueError("Collector deadline must be positive.")
        if self._limits.max_observations is not None and self._limits.max_observations < 1:
            raise ValueError("Collector observation limit must be positive.")
        if desired_account_total is not None and desired_account_total < target_count:
            raise ValueError("Desired account total is invalid.")
        run_id = claimed_run_id or self._persistence.create_run(account_id, trigger, target_count)
        deadline = (
            None
            if self._limits.deadline_seconds is None
            else self._clock() + self._limits.deadline_seconds
        )
        confirmed_advances = 0
        transition_operations = 0
        scroll_actions = 0
        committed_bytes = 0
        seen: set[str] = set()
        duplicate_skipped_count = 0
        observations = 0
        reason: str | None = None
        position = 1
        try:
            self._raise_if_cancel_requested(run_id)
            candidate = validate_candidate(self._feed.current())
            while True:
                self._raise_if_cancel_requested(run_id)
                if self._deadline_expired(deadline):
                    reason = "TOTAL_TIMEOUT_REACHED"
                    break
                if (
                    self._limits.max_observations is not None
                    and observations >= self._limits.max_observations
                ):
                    reason = "OBSERVATION_LIMIT_REACHED"
                    break
                observations += 1
                account_owned = False
                if desired_account_total is not None:
                    account_owned = self._persistence.account_has_durable_reel(
                        account_id, candidate.shortcode
                    )
                elif candidate.shortcode in seen:
                    reason = "DUPLICATE_REEL"
                    break
                seen.add(candidate.shortcode)
                self._record(position, "detect")
                self._feed.pause_current()
                self._record(position, "pause")
                status = self._persistence.reel_status(candidate.shortcode)
                if account_owned:
                    duplicate_skipped_count += 1
                    self._record(position, "duplicate_skipped")
                elif status in {
                    ReelPipelineStatus.SOURCE_READY.value,
                    ReelPipelineStatus.NORMALIZING.value,
                    ReelPipelineStatus.READY.value,
                }:
                    try:
                        self._persistence.commit_available(run_id, candidate)
                    except Exception:
                        reason = "DATABASE_WRITE_FAILED"
                        break
                    self._record(position, "db_commit")
                else:
                    temporary = self._storage.temporary_path(candidate.shortcode)
                    published = None
                    stage = "download"
                    download_attempted = False
                    db_committed = False
                    try:
                        self._raise_if_cancel_requested(run_id)
                        self._require_deadline(deadline)
                        download_attempted = True
                        self._downloader.download(candidate, temporary)
                        self._record(position, "download")
                        self._require_deadline(deadline)
                        stage = "validation"
                        validated = self._validator.validate(temporary)
                        self._record(position, "validation")
                        self._require_deadline(deadline)
                        if (
                            self._limits.max_run_bytes is not None
                            and committed_bytes + validated.byte_size > self._limits.max_run_bytes
                        ):
                            reason = "RUN_BYTE_LIMIT_EXCEEDED"
                            raise _CollectorLimitExceeded
                        stage = "publication"
                        self._raise_if_cancel_requested(run_id)
                        self._require_deadline(deadline)
                        published = self._storage.publish(
                            temporary,
                            source_object_key(candidate.shortcode),
                        )
                        self._record(position, "publication")
                        self._require_deadline(deadline)
                        stage = "database"
                        self._persistence.commit_source(
                            run_id, candidate, validated, published.object_key
                        )
                        db_committed = True
                        committed_bytes += validated.byte_size
                        self._record(position, "db_commit")
                        self._require_deadline(deadline)
                    except KeyboardInterrupt:
                        if (
                            not db_committed
                            and published is not None
                            and published.created_by_attempt
                        ):
                            try:
                                self._storage.delete(published.object_key)
                            except Exception:
                                pass
                        raise
                    except Exception as error:
                        compensation_failed = False
                        if (
                            not db_committed
                            and published is not None
                            and published.created_by_attempt
                        ):
                            try:
                                self._storage.delete(published.object_key)
                            except Exception:
                                compensation_failed = True
                        runtime_code = self._safe_exception_code(error)
                        if isinstance(error, _CollectorDeadlineExceeded):
                            reason = "TOTAL_TIMEOUT_REACHED"
                        elif reason == "RUN_BYTE_LIMIT_EXCEEDED":
                            pass
                        elif runtime_code == "STORAGE_OBJECT_CONFLICT":
                            reason = runtime_code
                        elif runtime_code is not None:
                            reason = runtime_code
                        elif published is not None:
                            reason = "DATABASE_WRITE_FAILED"
                            if compensation_failed:
                                reason = "DATABASE_WRITE_FAILED_COMPENSATION_FAILED"
                        elif stage == "validation":
                            reason = "VALIDATION_FAILED"
                        elif stage == "publication":
                            reason = "STORAGE_FAILED"
                        else:
                            reason = "DOWNLOAD_FAILED"
                        if not db_committed:
                            try:
                                self._persistence.record_failure(
                                    run_id,
                                    candidate,
                                    reason,
                                    download_attempted=download_attempted,
                                )
                            except Exception:
                                # The original operation failure remains authoritative.
                                pass
                        break
                    finally:
                        self._cleanup_temporary(temporary)
                committed, available, _failed, _status = self._persistence.summary(run_id)
                if committed + available >= target_count:
                    try:
                        completed = (
                            self._persistence.complete_if_account_durable_total(
                                run_id, desired_account_total
                            )
                            if desired_account_total is not None
                            else (self._persistence.complete_run(run_id) is None)
                        )
                        if not completed:
                            reason = "FINAL_DURABLE_TOTAL_MISMATCH"
                            raise RuntimeError(reason)
                    except Exception:
                        reason = reason or "DATABASE_WRITE_FAILED"
                        self._safe_fail_run(run_id, reason)
                        return self._summary(
                            run_id,
                            target_count,
                            confirmed_advances,
                            reason,
                            expected_status="failed",
                            observations=observations,
                            duplicate_skipped_count=duplicate_skipped_count,
                        )
                    return self._summary(
                        run_id,
                        target_count,
                        confirmed_advances,
                        None,
                        expected_status="completed",
                        observations=observations,
                        duplicate_skipped_count=duplicate_skipped_count,
                    )
                if self._deadline_expired(deadline):
                    reason = "TOTAL_TIMEOUT_REACHED"
                    break
                if confirmed_advances >= self._limits.max_advances:
                    reason = "ADVANCE_LIMIT_REACHED"
                    break
                if (
                    self._limits.max_transition_operations is not None
                    and transition_operations >= self._limits.max_transition_operations
                ):
                    reason = "ADVANCE_LIMIT_REACHED"
                    break
                if self._limits.cooldown_seconds:
                    self._require_deadline(deadline)
                    self._record(position, "cooldown")
                    self._sleep(self._limits.cooldown_seconds)
                if self._deadline_expired(deadline):
                    reason = "TOTAL_TIMEOUT_REACHED"
                    break
                transition_operations += 1
                self._raise_if_cancel_requested(run_id)
                (
                    next_candidate,
                    consumed_scroll_actions,
                    transition_reason,
                ) = self._confirm_transition(
                    position,
                    candidate.shortcode,
                    deadline,
                    remaining_scroll_actions=(
                        None
                        if self._limits.max_scroll_actions is None
                        else self._limits.max_scroll_actions - scroll_actions
                    ),
                )
                scroll_actions += consumed_scroll_actions
                if next_candidate is None:
                    reason = transition_reason or (
                        "TOTAL_TIMEOUT_REACHED"
                        if self._deadline_expired(deadline)
                        else "TRANSITION_FAILED"
                    )
                    break
                try:
                    candidate = validate_candidate(next_candidate)
                except InvalidReelCandidate:
                    reason = "INVALID_REEL_CANDIDATE"
                    break
                if desired_account_total is None and candidate.shortcode in seen:
                    reason = "DUPLICATE_REEL"
                    break
                confirmed_advances += 1
                self._record(position, "transition_confirmed")
                position += 1
            self._safe_fail_run(run_id, reason or "COLLECTOR_FAILED")
            return self._summary(
                run_id,
                target_count,
                confirmed_advances,
                reason,
                expected_status="failed",
                observations=observations,
                duplicate_skipped_count=duplicate_skipped_count,
            )
        except InvalidReelCandidate:
            self._safe_fail_run(run_id, "INVALID_REEL_CANDIDATE")
            return self._summary(
                run_id,
                target_count,
                confirmed_advances,
                "INVALID_REEL_CANDIDATE",
                expected_status="failed",
                observations=observations,
                duplicate_skipped_count=duplicate_skipped_count,
            )
        except KeyboardInterrupt:
            self._safe_cancel_run(run_id)
            return self._summary(
                run_id,
                target_count,
                confirmed_advances,
                "CANCELLED_BY_USER",
                expected_status="cancelled",
                observations=observations,
                duplicate_skipped_count=duplicate_skipped_count,
            )
        except Exception as error:
            safe_reason = self._safe_exception_code(error) or "COLLECTOR_FAILED"
            if safe_reason == "BROWSER_CLOSED":
                self._safe_cancel_run(run_id)
                return self._summary(
                    run_id,
                    target_count,
                    confirmed_advances,
                    safe_reason,
                    expected_status="cancelled",
                    observations=observations,
                    duplicate_skipped_count=duplicate_skipped_count,
                )
            self._safe_fail_run(run_id, safe_reason)
            return self._summary(
                run_id,
                target_count,
                confirmed_advances,
                safe_reason,
                expected_status="failed",
                observations=observations,
                duplicate_skipped_count=duplicate_skipped_count,
            )
        finally:
            try:
                self._feed.close()
            except Exception:
                pass

    def _summary(
        self,
        run_id: UUID,
        target_count: int,
        confirmed_advances: int,
        reason: str | None,
        *,
        expected_status: str | None = None,
        observations: int = 0,
        duplicate_skipped_count: int = 0,
    ) -> CollectorSummary:
        try:
            committed, available, failed, status = self._persistence.summary(run_id)
        except Exception:
            committed, available, failed = 0, 0, 0
            status = expected_status or "failed"
        if expected_status is not None:
            status = expected_status
        return CollectorSummary(
            run_id=run_id,
            status=status,
            target_count=target_count,
            source_committed_count=committed,
            already_available_count=available,
            failed_count=failed,
            confirmed_advances=confirmed_advances,
            observations=observations,
            duplicate_skipped_count=duplicate_skipped_count,
            stop_reason_code=reason,
        )

    def _record(self, position: int, event: str) -> None:
        try:
            self._recorder.record(position, event)
        except TypeError:
            # Compatibility for fixture recorders created before structured
            # transcripts; production recorders use the typed two-argument API.
            try:
                self._recorder.record(event)  # type: ignore[call-arg]
            except Exception:
                pass
        except Exception:
            pass

    def _deadline_expired(self, deadline: float | None) -> bool:
        return deadline is not None and self._clock() >= deadline

    def _require_deadline(self, deadline: float | None) -> None:
        if self._deadline_expired(deadline):
            raise _CollectorDeadlineExceeded

    def _raise_if_cancel_requested(self, run_id: UUID) -> None:
        probe = getattr(self._persistence, "cancellation_requested", None)
        if callable(probe) and probe(run_id):
            raise KeyboardInterrupt

    def _wait_for_next(self, shortcode: str, deadline: float | None):
        try:
            return self._feed.wait_for_next(
                shortcode,
                lambda: self._deadline_expired(deadline),
            )
        except TypeError:
            # Temporary compatibility for Stage 2 fixture ports. Runtime feeds
            # implement the cooperative deadline callback.
            return self._feed.wait_for_next(shortcode)

    def _confirm_transition(
        self,
        position: int,
        previous_shortcode: str,
        deadline: float | None,
        *,
        remaining_scroll_actions: int | None,
    ) -> tuple[ReelCandidate | None, int, str | None]:
        """One durable-commit-gated transition with at most one retry wheel."""

        diagnostic = {
            "position": position,
            "scroll_attempt_count": 0,
            "poll_count": 0,
            "unchanged_sample_count": 0,
            "missing_candidate_count": 0,
            "different_candidate_observed": False,
            "stable_sample_count": 0,
            "stable_media_identity_observed": False,
            "post_action_json_observed": False,
            "canonical_confirmation_observed": False,
            "canonical_dom_confirmation_observed": False,
            "canonical_queue_fallback_observed": False,
            "scroll_target_available": False,
            "scroll_target_in_viewport": False,
            "mouse_move_performed": False,
            "active_feed_target_available": False,
            "active_feed_target_in_viewport": False,
            "active_feed_target_hit_testable": False,
            "mobile_swipe_performed": False,
            "active_feed_probe_attempted": False,
            "active_feed_probe_evaluated": False,
            "active_feed_probe_failed": False,
            "active_feed_central_video_missing": False,
            **dict.fromkeys(HIT_TEST_DIAGNOSTIC_FLAGS, False),
            "stop_reason_code": None,
        }
        for attempt in (1, 2):
            if remaining_scroll_actions is not None and attempt > remaining_scroll_actions:
                diagnostic["stop_reason_code"] = "ADVANCE_LIMIT_REACHED"
                self._record_transition_diagnostics(diagnostic)
                return None, attempt - 1, "ADVANCE_LIMIT_REACHED"
            try:
                self._require_deadline(deadline)
                self._feed.advance()
            except _CollectorDeadlineExceeded:
                diagnostic["stop_reason_code"] = "TOTAL_TIMEOUT_REACHED"
                self._record_transition_diagnostics(diagnostic)
                return None, attempt - 1, "TOTAL_TIMEOUT_REACHED"
            except Exception as error:
                self._merge_scroll_target(diagnostic)
                diagnostic["stop_reason_code"] = (
                    self._safe_exception_code(error) or "TRANSITION_FAILED"
                )
                self._record_transition_diagnostics(diagnostic)
                raise
            self._merge_scroll_target(diagnostic)
            diagnostic["scroll_attempt_count"] = attempt
            self._record(position, "advance" if attempt == 1 else "advance_retry")
            try:
                next_candidate = self._wait_for_next(previous_shortcode, deadline)
            except Exception as error:
                self._merge_transition_sampling(diagnostic)
                diagnostic["stop_reason_code"] = (
                    self._safe_exception_code(error) or "TRANSITION_FAILED"
                )
                self._record_transition_diagnostics(diagnostic)
                raise
            self._merge_transition_sampling(diagnostic)
            if next_candidate is not None:
                diagnostic["stop_reason_code"] = None
                self._record_transition_diagnostics(diagnostic)
                return next_candidate, attempt, None
            if self._deadline_expired(deadline):
                diagnostic["stop_reason_code"] = "TOTAL_TIMEOUT_REACHED"
                self._record_transition_diagnostics(diagnostic)
                return None, attempt, "TOTAL_TIMEOUT_REACHED"
        diagnostic["stop_reason_code"] = "TRANSITION_FAILED"
        self._record_transition_diagnostics(diagnostic)
        return None, 2, "TRANSITION_FAILED"

    def _merge_transition_sampling(self, destination: dict[str, object]) -> None:
        sampling = getattr(self._feed, "transition_diagnostics", None)
        if not isinstance(sampling, TransitionSamplingDiagnostics):
            return
        destination["poll_count"] = int(destination["poll_count"]) + sampling.poll_count
        destination["unchanged_sample_count"] = (
            int(destination["unchanged_sample_count"]) + sampling.unchanged_sample_count
        )
        destination["missing_candidate_count"] = (
            int(destination["missing_candidate_count"]) + sampling.missing_candidate_count
        )
        destination["different_candidate_observed"] = bool(
            destination["different_candidate_observed"] or sampling.different_candidate_observed
        )
        destination["stable_sample_count"] = max(
            int(destination["stable_sample_count"]), sampling.stable_sample_count
        )
        for key in (
            "stable_media_identity_observed",
            "post_action_json_observed",
            "canonical_confirmation_observed",
            "canonical_dom_confirmation_observed",
            "canonical_queue_fallback_observed",
        ):
            destination[key] = bool(destination[key] or getattr(sampling, key))
        if isinstance(sampling.stop_reason_code, str):
            destination["stop_reason_code"] = sampling.stop_reason_code

    def _merge_scroll_target(self, destination: dict[str, object]) -> None:
        target = getattr(self._feed, "scroll_target_diagnostics", None)
        if not isinstance(target, ScrollTargetDiagnostics):
            return
        destination["scroll_target_available"] = bool(
            destination["scroll_target_available"] or target.scroll_target_available
        )
        destination["scroll_target_in_viewport"] = bool(
            destination["scroll_target_in_viewport"] or target.scroll_target_in_viewport
        )
        destination["mouse_move_performed"] = bool(
            destination["mouse_move_performed"] or target.mouse_move_performed
        )
        for key in (
            "active_feed_target_available",
            "active_feed_target_in_viewport",
            "active_feed_target_hit_testable",
            "mobile_swipe_performed",
            "active_feed_probe_attempted",
            "active_feed_probe_evaluated",
            "active_feed_probe_failed",
            "active_feed_central_video_missing",
            *HIT_TEST_DIAGNOSTIC_FLAGS,
        ):
            destination[key] = bool(destination[key] or getattr(target, key))

    def _record_transition_diagnostics(self, diagnostic: dict[str, object]) -> None:
        if len(self._transition_diagnostics) < self._limits.max_target:
            self._transition_diagnostics.append(dict(diagnostic))

    @staticmethod
    def _safe_exception_code(error: Exception) -> str | None:
        code = getattr(error, "code", None)
        value = getattr(code, "value", None)
        return value if isinstance(value, str) else None

    def _cleanup_temporary(self, temporary_path) -> None:
        try:
            self._storage.cleanup_temporary(temporary_path)
        except Exception:
            pass

    def _safe_fail_run(self, run_id: UUID, reason_code: str) -> None:
        try:
            self._persistence.fail_run(run_id, reason_code)
        except Exception:
            pass

    def _safe_cancel_run(self, run_id: UUID) -> None:
        try:
            self._persistence.cancel_run(run_id, "CANCELLED_BY_USER")
        except Exception:
            pass


class _CollectorLimitExceeded(Exception):
    pass


class _CollectorDeadlineExceeded(Exception):
    pass
