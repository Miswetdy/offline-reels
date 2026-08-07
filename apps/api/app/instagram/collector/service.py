"""Sequential, side-effect-oriented Collector orchestration."""

from dataclasses import dataclass
from uuid import UUID

from app.instagram.collector.canonical import (
    InvalidReelCandidate,
    source_object_key,
    validate_candidate,
)
from app.instagram.collector.contracts import (
    CollectorUnitOfWorkPort,
    DownloaderPort,
    EventRecorder,
    FeedPort,
    NullEventRecorder,
    SourceStoragePort,
    ValidatorPort,
)
from app.instagram.contracts import CollectionTrigger, ReelPipelineStatus


@dataclass(frozen=True)
class CollectorLimits:
    max_target: int = 5
    max_advances: int = 10


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
    ) -> None:
        self._persistence = persistence
        self._feed = feed
        self._downloader = downloader
        self._validator = validator
        self._storage = storage
        self._limits = limits
        self._recorder = recorder or NullEventRecorder()

    def collect(
        self,
        account_id: UUID,
        trigger: CollectionTrigger,
        target_count: int,
    ) -> CollectorSummary:
        if target_count < 1 or target_count > self._limits.max_target:
            raise ValueError("Target is outside the fixture Collector limit.")
        run_id = self._persistence.create_run(account_id, trigger, target_count)
        confirmed_advances = 0
        seen: set[str] = set()
        reason: str | None = None
        try:
            candidate = validate_candidate(self._feed.current())
            while True:
                if candidate.shortcode in seen:
                    reason = "DUPLICATE_REEL"
                    break
                seen.add(candidate.shortcode)
                self._record("detect")
                self._feed.pause_current()
                self._record("pause")
                status = self._persistence.reel_status(candidate.shortcode)
                if status in {
                    ReelPipelineStatus.SOURCE_READY.value,
                    ReelPipelineStatus.NORMALIZING.value,
                    ReelPipelineStatus.READY.value,
                }:
                    try:
                        self._persistence.commit_available(run_id, candidate)
                    except Exception:
                        reason = "DATABASE_WRITE_FAILED"
                        break
                    self._record("db_commit")
                else:
                    temporary = self._storage.temporary_path(candidate.shortcode)
                    published = None
                    stage = "download"
                    try:
                        self._downloader.download(candidate, temporary)
                        self._record("download")
                        stage = "validation"
                        validated = self._validator.validate(temporary)
                        self._record("validation")
                        stage = "publication"
                        published = self._storage.publish(
                            temporary,
                            source_object_key(candidate.shortcode),
                        )
                        self._record("publication")
                        stage = "database"
                        self._persistence.commit_source(
                            run_id, candidate, validated, published.object_key
                        )
                        self._record("db_commit")
                    except Exception:
                        compensation_failed = False
                        if published is not None and published.created_by_attempt:
                            try:
                                self._storage.delete(published.object_key)
                            except Exception:
                                compensation_failed = True
                        if published is not None:
                            reason = "DATABASE_WRITE_FAILED"
                            if compensation_failed:
                                reason = "DATABASE_WRITE_FAILED_COMPENSATION_FAILED"
                        elif stage == "validation":
                            reason = "VALIDATION_FAILED"
                        elif stage == "publication":
                            reason = "STORAGE_FAILED"
                        else:
                            reason = "DOWNLOAD_FAILED"
                        try:
                            self._persistence.record_failure(
                                run_id,
                                candidate,
                                reason,
                                download_attempted=True,
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
                        self._persistence.complete_run(run_id)
                    except Exception:
                        reason = "DATABASE_WRITE_FAILED"
                        self._safe_fail_run(run_id, reason)
                        return self._summary(
                            run_id,
                            target_count,
                            confirmed_advances,
                            reason,
                            expected_status="failed",
                        )
                    return self._summary(
                        run_id,
                        target_count,
                        confirmed_advances,
                        None,
                        expected_status="completed",
                    )
                if confirmed_advances >= self._limits.max_advances:
                    reason = "ADVANCE_LIMIT_REACHED"
                    break
                self._feed.advance()
                self._record("advance")
                next_candidate = self._feed.wait_for_next(candidate.shortcode)
                if next_candidate is None:
                    reason = "TRANSITION_FAILED"
                    break
                try:
                    candidate = validate_candidate(next_candidate)
                except InvalidReelCandidate:
                    reason = "INVALID_REEL_CANDIDATE"
                    break
                if candidate.shortcode in seen:
                    reason = "DUPLICATE_REEL"
                    break
                confirmed_advances += 1
                self._record("transition_confirmed")
            self._safe_fail_run(run_id, reason or "COLLECTOR_FAILED")
            return self._summary(
                run_id,
                target_count,
                confirmed_advances,
                reason,
                expected_status="failed",
            )
        except InvalidReelCandidate:
            self._safe_fail_run(run_id, "INVALID_REEL_CANDIDATE")
            return self._summary(
                run_id,
                target_count,
                confirmed_advances,
                "INVALID_REEL_CANDIDATE",
                expected_status="failed",
            )
        except Exception:
            self._safe_fail_run(run_id, "COLLECTOR_FAILED")
            return self._summary(
                run_id,
                target_count,
                confirmed_advances,
                "COLLECTOR_FAILED",
                expected_status="failed",
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
            stop_reason_code=reason,
        )

    def _record(self, event: str) -> None:
        try:
            self._recorder.record(event)
        except Exception:
            pass

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
