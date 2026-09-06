"""Typed ports and safe value objects for Collector orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.instagram.contracts import CollectionTrigger


@dataclass(frozen=True)
class ReelCandidate:
    shortcode: str
    canonical_url: str


@dataclass(frozen=True)
class ValidatedSource:
    sha256: str
    byte_size: int
    content_type: str


@dataclass(frozen=True)
class PublishedSource:
    object_key: str
    created_by_attempt: bool


@dataclass(frozen=True)
class TransitionSamplingDiagnostics:
    """Aggregate-only observations from one bounded feed transition wait."""

    poll_count: int = 0
    unchanged_sample_count: int = 0
    missing_candidate_count: int = 0
    different_candidate_observed: bool = False
    stable_sample_count: int = 0
    stable_media_identity_observed: bool = False
    post_action_json_observed: bool = False
    canonical_confirmation_observed: bool = False
    stop_reason_code: str | None = None


@dataclass(frozen=True)
class ScrollTargetDiagnostics:
    """Safe aggregate result of a targeted pointer-wheel preparation."""

    scroll_target_available: bool = False
    scroll_target_in_viewport: bool = False
    mouse_move_performed: bool = False
    active_feed_target_available: bool = False
    active_feed_target_in_viewport: bool = False
    active_feed_target_hit_testable: bool = False
    mobile_swipe_performed: bool = False
    active_feed_probe_attempted: bool = False
    active_feed_probe_evaluated: bool = False
    active_feed_probe_failed: bool = False
    active_feed_central_video_missing: bool = False
    hit_test_start_video_observed: bool = False
    hit_test_end_video_observed: bool = False
    hit_test_miss_null: bool = False
    hit_test_miss_control: bool = False
    hit_test_miss_other_video: bool = False
    hit_test_miss_video_ancestor: bool = False
    hit_test_miss_video_descendant: bool = False
    hit_test_miss_other_element: bool = False
    hit_test_video_pointer_events_none: bool = False
    hit_test_video_native_controls: bool = False


# Fixed allowlist shared by probe decoding and operator aggregation.
HIT_TEST_DIAGNOSTIC_FLAGS = (
    "hit_test_start_video_observed",
    "hit_test_end_video_observed",
    "hit_test_miss_null",
    "hit_test_miss_control",
    "hit_test_miss_other_video",
    "hit_test_miss_video_ancestor",
    "hit_test_miss_video_descendant",
    "hit_test_miss_other_element",
    "hit_test_video_pointer_events_none",
    "hit_test_video_native_controls",
)


class FeedPort(Protocol):
    def current(self) -> ReelCandidate: ...

    def pause_current(self) -> None: ...

    def advance(self) -> None: ...

    def wait_for_next(
        self,
        previous_shortcode: str,
        should_stop: Callable[[], bool] | None = None,
    ) -> ReelCandidate | None: ...

    @property
    def transition_diagnostics(self) -> TransitionSamplingDiagnostics: ...

    @property
    def scroll_target_diagnostics(self) -> ScrollTargetDiagnostics: ...

    def close(self) -> None: ...


class DownloaderPort(Protocol):
    def download(self, candidate: ReelCandidate, temporary_path: Path) -> None: ...


class ValidatorPort(Protocol):
    def validate(self, temporary_path: Path) -> ValidatedSource: ...


class SourceStoragePort(Protocol):
    """Publishes validated sources while the Collector retains temporary-file ownership.

    `temporary_path()` returns a Collector-owned path. Every terminal path,
    including successful publication, must call `cleanup_temporary()`; adapters
    therefore must make that cleanup idempotent if publication moved the file.
    """

    def temporary_path(self, shortcode: str) -> Path: ...

    def publish(self, temporary_path: Path, object_key: str) -> PublishedSource: ...

    def exists(self, object_key: str) -> bool: ...

    def delete(self, object_key: str) -> None: ...

    def cleanup_temporary(self, temporary_path: Path) -> None: ...


class CollectorUnitOfWorkPort(Protocol):
    """The Collector's explicit persistence boundary; methods commit atomically."""

    def create_run(
        self,
        account_id: UUID,
        trigger: CollectionTrigger,
        target_count: int,
    ) -> UUID: ...

    def reel_status(self, shortcode: str) -> str | None: ...

    def account_durable_count(self, account_id: UUID) -> int: ...

    def account_has_durable_reel(self, account_id: UUID, shortcode: str) -> bool: ...

    def commit_available(self, run_id: UUID, candidate: ReelCandidate) -> None: ...

    def commit_source(
        self,
        run_id: UUID,
        candidate: ReelCandidate,
        source: ValidatedSource,
        object_key: str,
    ) -> None: ...

    def record_failure(
        self,
        run_id: UUID,
        candidate: ReelCandidate,
        reason_code: str,
        *,
        download_attempted: bool,
    ) -> None: ...

    def fail_run(self, run_id: UUID, reason_code: str) -> None: ...

    def cancel_run(self, run_id: UUID, reason_code: str) -> CancelRunOutcome: ...

    def complete_run(self, run_id: UUID) -> None: ...

    def complete_if_account_durable_total(self, run_id: UUID, desired_total: int) -> bool: ...

    def summary(self, run_id: UUID) -> tuple[int, int, int, str]: ...


class EventRecorder(Protocol):
    def record(self, position: int, event: str) -> None: ...


class NullEventRecorder:
    def record(self, position: int, event: str) -> None:
        del position, event


class CancelRunOutcome(StrEnum):
    CANCELLED = "cancelled"
    NOT_FOUND = "not_found"
    ALREADY_TERMINAL = "already_terminal"
