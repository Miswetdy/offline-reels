"""Durable, intentionally small worker for source-to-canonical publication."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.instagram import InstagramNormalizationJob, InstagramReel
from app.db.models.video import Video
from app.instagram.contracts import NormalizationJobStatus, ReasonCode, ReelPipelineStatus
from app.media.compatibility import is_canonical_media
from app.media.errors import (
    MediaCompatibilityError,
    MediaDecodeError,
    MediaDecodeTimeoutError,
    MediaNormalizationCommandError,
    MediaNormalizationTimeoutError,
    MediaProbeError,
    MediaProbeTimeoutError,
)
from app.media.normalize import normalize_video, validate_decode
from app.media.probe import probe_media
from app.repositories.videos import VideoRepository
from app.storage.base import StorageObjectNotFound, VideoStorage

MAX_NORMALIZATION_ATTEMPTS = 3
LEASE_SECONDS = 30 * 60
STAGING_PREFIX = "instagram-normalizer-staging"


class WorkerCancelled(Exception):
    """Cooperative cancellation; this text is never persisted or emitted."""


class FinalObjectConflict(Exception):
    pass


@dataclass(frozen=True)
class ClaimedNormalizationJob:
    job_id: UUID
    reel_id: UUID
    shortcode: str
    source_object_key: str
    source_sha256: str
    source_byte_size: int
    attempt_count: int
    staging_prefix: str


@dataclass(frozen=True)
class WorkerStatus:
    pending: int
    running: int
    completed: int
    failed: int
    source_ready: int
    normalizing: int
    ready: int
    cleanup_pending: int


class InstagramNormalizerWorker:
    """Claims one PostgreSQL job at a time and never exposes staging media."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: VideoStorage,
        *,
        worker_id: str | None = None,
        cancellation: Event | None = None,
        lease_seconds: int = LEASE_SECONDS,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self._sessions = sessions
        self._storage = storage
        # A generated opaque UUID has no hostname, account name or other PII.
        self._worker_id = worker_id or str(uuid4())
        self._cancelled = cancellation or Event()
        self._lease_seconds = lease_seconds
        self._progress_callback = progress
        self._videos = VideoRepository()

    def status(self) -> WorkerStatus:
        with self._sessions() as session:
            def count_job(status: NormalizationJobStatus) -> int:
                return int(
                    session.scalar(
                        select(func.count()).select_from(InstagramNormalizationJob).where(
                            InstagramNormalizationJob.status == status.value
                        )
                    )
                    or 0
                )

            def count_reel(status: ReelPipelineStatus) -> int:
                return int(
                    session.scalar(
                        select(func.count()).select_from(InstagramReel).where(
                            InstagramReel.pipeline_status == status.value
                        )
                    )
                    or 0
                )

            return WorkerStatus(
                pending=count_job(NormalizationJobStatus.PENDING),
                running=count_job(NormalizationJobStatus.RUNNING),
                completed=count_job(NormalizationJobStatus.COMPLETED),
                failed=count_job(NormalizationJobStatus.FAILED),
                source_ready=count_reel(ReelPipelineStatus.SOURCE_READY),
                normalizing=count_reel(ReelPipelineStatus.NORMALIZING),
                ready=count_reel(ReelPipelineStatus.READY),
                cleanup_pending=int(
                    session.scalar(
                        select(func.count()).select_from(InstagramReel).where(
                            InstagramReel.source_cleanup_pending.is_(True)
                        )
                    )
                    or 0
                ),
            )

    def verify(self) -> dict[str, int]:
        """Read-only database/object-store aggregate consistency report."""

        status = self.status()
        with self._sessions() as session:
            source_keys = list(
                session.scalars(
                    select(InstagramReel.source_object_key).where(
                        InstagramReel.pipeline_status == ReelPipelineStatus.SOURCE_READY.value,
                        InstagramReel.source_object_key.is_not(None),
                    )
                )
            )
            final_keys = list(
                session.scalars(
                    select(Video.object_key)
                    .join(InstagramReel, InstagramReel.video_id == Video.id)
                    .where(InstagramReel.pipeline_status == ReelPipelineStatus.READY.value)
                )
            )
            videos = int(session.scalar(select(func.count()).select_from(Video)) or 0)
        missing_sources = sum(not self._object_exists(key) for key in source_keys)
        missing_final = sum(not self._object_exists(key) for key in final_keys)
        return {
            "source_ready": status.source_ready,
            "pending": status.pending,
            "running": status.running,
            "completed": status.completed,
            "failed": status.failed,
            "ready": status.ready,
            "videos": videos,
            "source_objects": len(self._storage.list_prefix("instagram-sources/")),
            "final_objects": len(self._storage.list_prefix("videos/")),
            "staging_objects": len(self._storage.list_prefix(f"{STAGING_PREFIX}/")),
            "missing_source_ready_objects": missing_sources,
            "missing_ready_final_objects": missing_final,
            "cleanup_pending": status.cleanup_pending,
        }

    def run_once(self) -> bool:
        if self._cancelled.is_set():
            return False
        claimed = self.claim()
        if claimed is None:
            return False
        self._emit(claimed, "claimed")
        try:
            self._process(claimed)
        except WorkerCancelled:
            self._finish_failure(claimed, ReasonCode.WORKER_CANCELLED, retryable=True)
            self._emit(claimed, "failed", ReasonCode.WORKER_CANCELLED)
        except Exception as error:  # classification, not exception persistence/logging
            reason, retryable = _classify_error(error)
            self._finish_failure(claimed, reason, retryable=retryable)
            self._emit(claimed, "failed", reason)
        finally:
            self._cleanup_staging(claimed.staging_prefix)
        return True

    def claim(self) -> ClaimedNormalizationJob | None:
        self._raise_if_cancelled()
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            row = session.execute(
                select(InstagramNormalizationJob, InstagramReel)
                .join(InstagramReel, InstagramNormalizationJob.reel_id == InstagramReel.id)
                .where(
                    InstagramNormalizationJob.status == NormalizationJobStatus.PENDING.value,
                    InstagramReel.pipeline_status == ReelPipelineStatus.SOURCE_READY.value,
                )
                .order_by(InstagramNormalizationJob.created_at, InstagramNormalizationJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if row is None:
                return None
            job, reel = row
            next_attempt = job.attempt_count + 1
            if next_attempt > MAX_NORMALIZATION_ATTEMPTS:
                job.status = NormalizationJobStatus.FAILED.value
                job.reason_code = ReasonCode.RETRY_EXHAUSTED.value
                job.completed_at = now
                reel.pipeline_status = ReelPipelineStatus.FAILED.value
                reel.failure_reason_code = ReasonCode.RETRY_EXHAUSTED.value
                reel.failed_at = now
                return None
            staging_prefix = f"{STAGING_PREFIX}/{job.id}/{next_attempt}"
            job.status = NormalizationJobStatus.RUNNING.value
            job.attempt_count = next_attempt
            job.claimed_at = now
            job.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            job.worker_id = self._worker_id
            job.staging_prefix = staging_prefix
            reel.pipeline_status = ReelPipelineStatus.NORMALIZING.value
            return ClaimedNormalizationJob(
                job_id=job.id,
                reel_id=reel.id,
                shortcode=reel.shortcode,
                source_object_key=_required(reel.source_object_key),
                source_sha256=_required(reel.source_sha256),
                source_byte_size=_required(reel.source_byte_size),
                attempt_count=next_attempt,
                staging_prefix=staging_prefix,
            )

    def reconcile(self) -> dict[str, int]:
        """Recover expired claims and retry only post-commit source cleanup."""

        now = datetime.now(UTC)
        stale_prefixes: list[str] = []
        recovered = 0
        with self._sessions.begin() as session:
            stale = list(
                session.scalars(
                    select(InstagramNormalizationJob)
                    .where(
                        InstagramNormalizationJob.status == NormalizationJobStatus.RUNNING.value,
                        InstagramNormalizationJob.lease_expires_at.is_not(None),
                        InstagramNormalizationJob.lease_expires_at < now,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for job in stale:
                reel = session.get(InstagramReel, job.reel_id)
                if reel is None:
                    continue
                if job.staging_prefix:
                    stale_prefixes.append(job.staging_prefix)
                job.status = NormalizationJobStatus.FAILED.value
                job.reason_code = ReasonCode.STALE_LEASE_RECOVERED.value
                job.completed_at = now
                job.lease_expires_at = None
                job.worker_id = None
                if job.attempt_count < MAX_NORMALIZATION_ATTEMPTS:
                    reel.pipeline_status = ReelPipelineStatus.SOURCE_READY.value
                    session.add(
                        InstagramNormalizationJob(
                            reel_id=reel.id,
                            status=NormalizationJobStatus.PENDING.value,
                            attempt_count=job.attempt_count,
                        )
                    )
                else:
                    reel.pipeline_status = ReelPipelineStatus.FAILED.value
                    reel.failure_reason_code = ReasonCode.RETRY_EXHAUSTED.value
                    reel.failed_at = now
                recovered += 1
        for prefix in stale_prefixes:
            self._cleanup_staging(prefix)
        cleaned = self._reconcile_source_cleanup()
        return {"stale_recovered": recovered, "sources_cleaned": cleaned}

    def _process(self, claimed: ClaimedNormalizationJob) -> None:
        self._raise_if_cancelled()
        with tempfile.TemporaryDirectory(prefix="offline-reels-normalizer-") as temporary:
            workspace = Path(temporary)
            source_path = workspace / "source.mp4"
            self._download_and_verify_source(claimed, source_path)
            self._emit(claimed, "source_verified")
            self._raise_if_cancelled()
            # Existing media normalizer performs source probe/full decode, strategy,
            # output probe/full decode and canonical compatibility validation.
            with normalize_video(source_path) as normalized:
                self._emit(claimed, normalized.strategy.value)
                self._raise_if_cancelled()
                if not _is_worker_canonical(normalized.probe):
                    raise MediaCompatibilityError("Canonical worker output requires AAC audio.")
                output_sha256, output_size = _hash_file(normalized.output_path)
                staging_key = f"{claimed.staging_prefix}/canonical.mp4"
                self._storage.upload_file(staging_key, normalized.output_path, "video/mp4")
                self._emit(claimed, "normalized")
                final_key = f"videos/{output_sha256}.mp4"
                created_final = self._publish_final(staging_key, final_key, normalized.output_path)
                self._emit(claimed, "final_published")
                self._raise_if_cancelled()
                try:
                    self._commit_ready(
                        claimed,
                        final_key=final_key,
                        output_sha256=output_sha256,
                        output_size=output_size,
                        strategy=normalized.strategy.value,
                        original_codec=normalized.original_probe.video_codec,
                        probe=normalized.probe,
                    )
                except Exception:
                    self._compensate_final_if_unreferenced(final_key, created_final)
                    raise
                self._emit(claimed, "db_committed")
                self._cleanup_source_after_commit(claimed)
                self._emit(claimed, "completed")

    def _download_and_verify_source(
        self, claimed: ClaimedNormalizationJob, source_path: Path
    ) -> None:
        metadata = self._storage.stat(claimed.source_object_key)
        if metadata.byte_size != claimed.source_byte_size:
            raise SourceSizeMismatch
        self._storage.download_file(claimed.source_object_key, source_path)
        actual_sha256, actual_size = _hash_file(source_path)
        if actual_size != claimed.source_byte_size:
            raise SourceSizeMismatch
        if actual_sha256 != claimed.source_sha256:
            raise SourceHashMismatch
        probe_media(source_path)

    def _publish_final(
        self, staging_key: str, final_key: str, output_path: Path
    ) -> bool:
        output_sha256, output_size = _hash_file(output_path)
        try:
            existing = self._storage.stat(final_key)
        except StorageObjectNotFound:
            self._storage.copy(staging_key, final_key)
            try:
                self._verify_final(final_key, output_sha256, output_size)
            except Exception:
                self._compensate_final_if_unreferenced(final_key, created_final=True)
                raise
            return True
        if existing.byte_size != output_size:
            raise FinalObjectConflict
        self._verify_final(final_key, output_sha256, output_size)
        return False

    def _verify_final(self, final_key: str, expected_sha256: str, expected_size: int) -> None:
        with tempfile.TemporaryDirectory(prefix="offline-reels-normalizer-verify-") as temporary:
            candidate = Path(temporary) / "canonical.mp4"
            self._storage.download_file(final_key, candidate)
            actual_sha256, actual_size = _hash_file(candidate)
            if actual_sha256 != expected_sha256 or actual_size != expected_size:
                raise FinalObjectConflict
            probe = probe_media(candidate)
            validate_decode(candidate)
            if not _is_worker_canonical(probe):
                raise FinalObjectConflict

    def _commit_ready(
        self,
        claimed: ClaimedNormalizationJob,
        *,
        final_key: str,
        output_sha256: str,
        output_size: int,
        strategy: str,
        original_codec: str,
        probe,
    ) -> None:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            job = session.get(InstagramNormalizationJob, claimed.job_id, with_for_update=True)
            reel = session.get(InstagramReel, claimed.reel_id, with_for_update=True)
            if job is None or reel is None or not self._is_owned_running(job):
                raise WorkerCancelled
            result = self._videos.upsert(
                session,
                title=f"Instagram Reel {claimed.shortcode}",
                object_key=final_key,
                content_type="video/mp4",
                byte_size=output_size,
                normalization_strategy=strategy,
                original_video_codec=original_codec.lower(),
                normalized_video_codec=probe.video_codec.lower(),
                width=probe.width,
                height=probe.height,
                duration_ms=round(_required(probe.duration_seconds) * 1000),
                file_size_bytes=output_size,
                has_audio=bool(probe.audio_codecs),
                normalized_at=now,
                content_sha256=output_sha256,
            )
            video = result.video
            if video.content_sha256 not in {None, output_sha256} or video.byte_size != output_size:
                raise FinalObjectConflict
            reel.video_id = video.id
            reel.pipeline_status = ReelPipelineStatus.READY.value
            reel.ready_at = now
            reel.failure_reason_code = None
            # It stays true until object deletion succeeds, including crash windows.
            reel.source_cleanup_pending = True
            job.status = NormalizationJobStatus.COMPLETED.value
            job.reason_code = None
            job.completed_at = now
            job.lease_expires_at = None
            job.worker_id = None

    def _cleanup_source_after_commit(self, claimed: ClaimedNormalizationJob) -> None:
        try:
            self._storage.remove(claimed.source_object_key)
        except StorageObjectNotFound:
            pass
        except Exception:
            return
        with self._sessions.begin() as session:
            reel = session.get(InstagramReel, claimed.reel_id, with_for_update=True)
            if reel is not None and reel.pipeline_status == ReelPipelineStatus.READY.value:
                reel.source_cleanup_pending = False

    def _reconcile_source_cleanup(self) -> int:
        with self._sessions() as session:
            rows = list(
                session.scalars(
                    select(InstagramReel).where(
                        InstagramReel.pipeline_status == ReelPipelineStatus.READY.value,
                        InstagramReel.source_cleanup_pending.is_(True),
                    )
                )
            )
        cleaned = 0
        for reel in rows:
            if not reel.source_object_key:
                continue
            try:
                self._storage.remove(reel.source_object_key)
            except StorageObjectNotFound:
                pass
            except Exception:
                continue
            with self._sessions.begin() as session:
                current = session.get(InstagramReel, reel.id, with_for_update=True)
                if current is not None and current.source_cleanup_pending:
                    current.source_cleanup_pending = False
                    cleaned += 1
        return cleaned

    def _finish_failure(
        self, claimed: ClaimedNormalizationJob, reason: ReasonCode, *, retryable: bool) -> None:
        now = datetime.now(UTC)
        try:
            with self._sessions.begin() as session:
                job = session.get(InstagramNormalizationJob, claimed.job_id, with_for_update=True)
                reel = session.get(InstagramReel, claimed.reel_id, with_for_update=True)
                if job is None or reel is None or not self._is_owned_running(job):
                    return
                job.status = NormalizationJobStatus.FAILED.value
                job.reason_code = reason.value
                job.completed_at = now
                job.lease_expires_at = None
                job.worker_id = None
                if retryable and job.attempt_count < MAX_NORMALIZATION_ATTEMPTS:
                    reel.pipeline_status = ReelPipelineStatus.SOURCE_READY.value
                    reel.failure_reason_code = reason.value
                    session.add(
                        InstagramNormalizationJob(
                            reel_id=reel.id,
                            status=NormalizationJobStatus.PENDING.value,
                            attempt_count=job.attempt_count,
                        )
                    )
                else:
                    reel.pipeline_status = ReelPipelineStatus.FAILED.value
                    reel.failure_reason_code = (
                        ReasonCode.RETRY_EXHAUSTED.value if retryable else reason.value
                    )
                    reel.failed_at = now
        except SQLAlchemyError:
            # A lease/reconciler is deliberately safer than hiding a DB failure.
            return

    def _compensate_final_if_unreferenced(self, final_key: str, created_final: bool) -> None:
        if not created_final:
            return
        try:
            with self._sessions() as session:
                referenced = session.scalar(select(Video.id).where(Video.object_key == final_key))
            if referenced is None:
                self._storage.remove(final_key)
        except Exception:
            return

    def _cleanup_staging(self, prefix: str) -> None:
        try:
            for key in self._storage.list_prefix(f"{prefix}/"):
                self._storage.remove(key)
        except Exception:
            return

    def _is_owned_running(self, job: InstagramNormalizationJob) -> bool:
        return (
            job.status == NormalizationJobStatus.RUNNING.value and job.worker_id == self._worker_id
        )

    def _object_exists(self, key: str) -> bool:
        try:
            self._storage.stat(key)
        except StorageObjectNotFound:
            return False
        return True

    def _raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise WorkerCancelled

    def _emit(
        self, claimed: ClaimedNormalizationJob, event: str, reason: ReasonCode | None = None
    ) -> None:
        if self._progress_callback is not None:
            self._progress_callback(
                {
                    "job_id": str(claimed.job_id),
                    "reel_id": str(claimed.reel_id),
                    "shortcode": claimed.shortcode,
                    "attempt": claimed.attempt_count,
                    "event": event,
                    **({"reason_code": reason.value} if reason else {}),
                }
            )


class SourceHashMismatch(Exception):
    pass


class SourceSizeMismatch(Exception):
    pass


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _required(value):
    if value is None:
        raise ValueError("required durable field missing")
    return value


def _classify_error(error: Exception) -> tuple[ReasonCode, bool]:
    if isinstance(error, StorageObjectNotFound):
        return ReasonCode.SOURCE_MISSING, True
    if isinstance(error, SourceHashMismatch):
        return ReasonCode.SOURCE_HASH_MISMATCH, False
    if isinstance(error, SourceSizeMismatch):
        return ReasonCode.SOURCE_SIZE_MISMATCH, False
    if isinstance(error, (MediaProbeError, MediaProbeTimeoutError)):
        return ReasonCode.FFPROBE_FAILED, False
    if isinstance(error, (MediaDecodeError, MediaDecodeTimeoutError)):
        return ReasonCode.FULL_DECODE_FAILED, False
    if isinstance(error, MediaCompatibilityError):
        return ReasonCode.INCOMPATIBLE_OUTPUT, False
    if isinstance(error, (MediaNormalizationCommandError, MediaNormalizationTimeoutError)):
        return ReasonCode.NORMALIZATION_FAILED, False
    if isinstance(error, FinalObjectConflict):
        return ReasonCode.FINAL_OBJECT_CONFLICT, False
    if isinstance(error, SQLAlchemyError):
        return ReasonCode.POSTGRES_COMMIT_FAILURE, True
    if isinstance(error, WorkerCancelled):
        return ReasonCode.WORKER_CANCELLED, True
    return ReasonCode.MINIO_TRANSIENT_FAILURE, True


def _is_worker_canonical(probe) -> bool:
    """The catalog contract requires AAC; generic seed normalization may not."""

    return bool(probe.audio_codecs) and is_canonical_media(probe)
