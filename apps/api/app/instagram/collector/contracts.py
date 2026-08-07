"""Typed ports and safe value objects for Collector orchestration."""

from dataclasses import dataclass
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


class FeedPort(Protocol):
    def current(self) -> ReelCandidate: ...

    def pause_current(self) -> None: ...

    def advance(self) -> None: ...

    def wait_for_next(self, previous_shortcode: str) -> ReelCandidate | None: ...

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

    def complete_run(self, run_id: UUID) -> None: ...

    def summary(self, run_id: UUID) -> tuple[int, int, int, str]: ...


class EventRecorder(Protocol):
    def record(self, event: str) -> None: ...


class NullEventRecorder:
    def record(self, event: str) -> None:
        del event
