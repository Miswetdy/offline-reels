"""Network-free adapters used only by the fixture command and tests."""

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models.instagram import InstagramReel
from app.instagram.collector.contracts import (
    DownloaderPort,
    FeedPort,
    PublishedSource,
    ReelCandidate,
    ScrollTargetDiagnostics,
    SourceStoragePort,
    TransitionSamplingDiagnostics,
    ValidatedSource,
    ValidatorPort,
)
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.contracts import DownloadAuthMode, RunItemOutcome


class FixtureFailure(RuntimeError):
    pass


class FixtureRollbackFailingPersistence(CollectorPersistence):
    """Injects a failure after source changes were added, before transaction commit."""

    @staticmethod
    def _add_item(
        session: Session,
        run_id,
        reel: InstagramReel,
        outcome: RunItemOutcome,
        auth_mode: DownloadAuthMode | None,
        reason_code: str | None = None,
    ) -> None:
        CollectorPersistence._add_item(
            session,
            run_id,
            reel,
            outcome,
            auth_mode,
            reason_code,
        )
        if outcome is RunItemOutcome.SOURCE_COMMITTED:
            raise FixtureFailure("fixture commit failure after transaction mutations")


class FixtureFeed(FeedPort):
    def __init__(
        self,
        candidates: list[ReelCandidate],
        *,
        transition_timeout: bool = False,
    ) -> None:
        self._candidates = candidates
        self._index = 0
        self._transition_timeout = transition_timeout
        self._transition_diagnostics = TransitionSamplingDiagnostics()
        self._scroll_target_diagnostics = ScrollTargetDiagnostics()

    def current(self) -> ReelCandidate:
        return self._candidates[self._index]

    def pause_current(self) -> None:
        return None

    def advance(self) -> None:
        self._scroll_target_diagnostics = ScrollTargetDiagnostics(True, True, True)
        if self._index < len(self._candidates) - 1:
            self._index += 1

    @property
    def transition_diagnostics(self) -> TransitionSamplingDiagnostics:
        return self._transition_diagnostics

    @property
    def scroll_target_diagnostics(self) -> ScrollTargetDiagnostics:
        return self._scroll_target_diagnostics

    def wait_for_next(self, previous_shortcode: str, should_stop=None) -> ReelCandidate | None:
        if should_stop is not None and should_stop():
            self._transition_diagnostics = TransitionSamplingDiagnostics(
                poll_count=1,
                stop_reason_code="TOTAL_TIMEOUT_REACHED",
            )
            return None
        if self._transition_timeout:
            self._transition_diagnostics = TransitionSamplingDiagnostics(
                poll_count=1,
                unchanged_sample_count=1,
                stop_reason_code="TRANSITION_TIMEOUT",
            )
            return None
        candidate = self.current()
        if candidate.shortcode == previous_shortcode:
            self._transition_diagnostics = TransitionSamplingDiagnostics(
                poll_count=1,
                unchanged_sample_count=1,
                stop_reason_code="TRANSITION_TIMEOUT",
            )
            return None
        self._transition_diagnostics = TransitionSamplingDiagnostics(
            poll_count=2,
            different_candidate_observed=True,
            stable_sample_count=2,
        )
        return candidate

    def close(self) -> None:
        return None


class FixtureDownloader(DownloaderPort):
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def download(self, candidate: ReelCandidate, temporary_path: Path) -> None:
        if self._fail:
            raise FixtureFailure("fixture download failure")
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(f"fixture-source:{candidate.shortcode}".encode())


class FixtureValidator(ValidatorPort):
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def validate(self, temporary_path: Path) -> ValidatedSource:
        if self._fail:
            raise FixtureFailure("fixture validation failure")
        content = temporary_path.read_bytes()
        if not content:
            raise FixtureFailure("fixture source is empty")
        return ValidatedSource(
            sha256=hashlib.sha256(content).hexdigest(),
            byte_size=len(content),
            content_type="video/mp4",
        )


class LocalFixtureSourceStorage(SourceStoragePort):
    def __init__(
        self,
        root: Path,
        *,
        fail_publish: bool = False,
        fail_delete: bool = False,
    ) -> None:
        self._root = root.resolve()
        self._temporary = self._root / ".temporary"
        self._fail_publish = fail_publish
        self._fail_delete = fail_delete

    def temporary_path(self, shortcode: str) -> Path:
        return self._temporary / f"{shortcode}.part"

    def publish(self, temporary_path: Path, object_key: str) -> PublishedSource:
        if self._fail_publish:
            raise FixtureFailure("fixture storage failure")
        destination = self._resolve(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            self.cleanup_temporary(temporary_path)
            return PublishedSource(object_key=object_key, created_by_attempt=False)
        temporary_path.replace(destination)
        return PublishedSource(object_key=object_key, created_by_attempt=True)

    def exists(self, object_key: str) -> bool:
        return self._resolve(object_key).is_file()

    def delete(self, object_key: str) -> None:
        if self._fail_delete:
            raise FixtureFailure("fixture compensation failure")
        self._resolve(object_key).unlink(missing_ok=True)

    def cleanup_temporary(self, temporary_path: Path) -> None:
        temporary_path.unlink(missing_ok=True)

    def _resolve(self, object_key: str) -> Path:
        candidate = (self._root / object_key).resolve()
        if candidate == self._root or self._root not in candidate.parents:
            raise ValueError("Unsafe fixture object key.")
        return candidate
