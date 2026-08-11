"""SQLAlchemy transaction boundary for Collector source commits."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    InstagramCollectionRunItem,
    InstagramNormalizationJob,
    InstagramReel,
)
from app.instagram.collector.contracts import CancelRunOutcome, ReelCandidate, ValidatedSource
from app.instagram.contracts import (
    AccountStatus,
    CollectionRunStatus,
    CollectionTrigger,
    DownloadAuthMode,
    NormalizationJobStatus,
    ReelPipelineStatus,
    RunItemOutcome,
)
from app.instagram.transitions import (
    ACCOUNT_TRANSITIONS,
    REEL_PIPELINE_TRANSITIONS,
    require_transition,
)


@dataclass(frozen=True)
class DurableReelSnapshot:
    reel_id: UUID
    object_key: str
    sha256: str
    byte_size: int


class CollectorPersistence:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def create_run(self, account_id: UUID, trigger: CollectionTrigger, target_count: int) -> UUID:
        run_id = uuid4()
        with self._sessions.begin() as session:
            session.add(
                InstagramCollectionRun(
                    id=run_id,
                    account_id=account_id,
                    trigger=trigger.value,
                    status=CollectionRunStatus.RUNNING.value,
                    target_count=target_count,
                    started_at=datetime.now(UTC),
                )
            )
        return run_id

    def claim_queued_run(self, account_id: UUID) -> InstagramCollectionRun | None:
        """Claim one API-queued command; runtime startup stays outside FastAPI."""
        with self._sessions.begin() as session:
            item = session.scalar(
                select(InstagramCollectionRun)
                .where(
                    InstagramCollectionRun.account_id == account_id,
                    InstagramCollectionRun.status == CollectionRunStatus.QUEUED.value,
                    InstagramCollectionRun.cancel_requested_at.is_(None),
                )
                .order_by(InstagramCollectionRun.created_at, InstagramCollectionRun.id)
                .with_for_update(skip_locked=True)
            )
            if item is None:
                return None
            item.status = CollectionRunStatus.RUNNING.value
            item.started_at = datetime.now(UTC)
            session.flush()
            session.expunge(item)
            return item

    def cancellation_requested(self, run_id: UUID) -> bool:
        with self._sessions() as session:
            item = session.get(InstagramCollectionRun, run_id)
            return bool(item is None or item.cancel_requested_at is not None)

    def ensure_account(self, account_id: UUID) -> None:
        with self._sessions.begin() as session:
            if session.get(InstagramAccount, account_id) is None:
                session.add(
                    InstagramAccount(id=account_id, status=AccountStatus.DISCONNECTED.value)
                )

    def set_account_status(
        self,
        account_id: UUID,
        status: AccountStatus,
        reason_code: str | None = None,
    ) -> None:
        with self._sessions.begin() as session:
            account = session.get(InstagramAccount, account_id)
            if account is None:
                account = InstagramAccount(id=account_id, status=AccountStatus.DISCONNECTED.value)
                session.add(account)
                session.flush()
            current = AccountStatus(account.status)
            if current is not status:
                require_transition(ACCOUNT_TRANSITIONS, current, status)
                account.status = status.value
            account.reason_code = reason_code
            now = datetime.now(UTC)
            if status is AccountStatus.CONNECTED:
                account.last_connected_at = now
            elif status is AccountStatus.REAUTH_REQUIRED:
                account.reauth_required_at = now

    def account_status(self, account_id: UUID) -> AccountStatus:
        with self._sessions() as session:
            account = session.get(InstagramAccount, account_id)
            return AccountStatus.DISCONNECTED if account is None else AccountStatus(account.status)

    def active_run_exists(self, account_id: UUID) -> bool:
        with self._sessions() as session:
            return (
                session.scalar(
                    select(InstagramCollectionRun.id).where(
                        InstagramCollectionRun.account_id == account_id,
                        InstagramCollectionRun.status.in_(
                            (CollectionRunStatus.QUEUED.value, CollectionRunStatus.RUNNING.value)
                        ),
                    )
                )
                is not None
            )

    def reel_status(self, shortcode: str) -> str | None:
        with self._sessions() as session:
            statement = select(InstagramReel.pipeline_status).where(
                InstagramReel.shortcode == shortcode
            )
            return session.scalar(statement)

    def account_durable_count(self, account_id: UUID) -> int:
        """Count distinct durable Reels acquired by this account's run history."""

        with self._sessions() as session:
            return self._account_durable_count(session, account_id)

    def account_has_durable_reel(self, account_id: UUID, shortcode: str) -> bool:
        """Ownership is run-item history, never global Reel presence alone."""

        with self._sessions() as session:
            return (
                session.scalar(
                    select(InstagramReel.id)
                    .join(
                        InstagramCollectionRunItem,
                        InstagramCollectionRunItem.reel_id == InstagramReel.id,
                    )
                    .join(
                        InstagramCollectionRun,
                        InstagramCollectionRun.id == InstagramCollectionRunItem.run_id,
                    )
                    .where(
                        InstagramCollectionRun.account_id == account_id,
                        InstagramReel.shortcode == shortcode,
                        InstagramReel.pipeline_status.in_(self._durable_statuses()),
                        InstagramReel.source_object_key.is_not(None),
                        InstagramReel.source_sha256.is_not(None),
                        InstagramReel.source_byte_size.is_not(None),
                        InstagramCollectionRunItem.outcome.in_(self._acquisition_outcomes()),
                    )
                )
                is not None
            )

    def account_durable_baseline(self, account_id: UUID) -> tuple[DurableReelSnapshot, ...]:
        """Immutable safe metadata used to protect prior account acquisitions."""

        with self._sessions() as session:
            rows = session.execute(
                select(
                    InstagramReel.id,
                    InstagramReel.source_object_key,
                    InstagramReel.source_sha256,
                    InstagramReel.source_byte_size,
                )
                .join(
                    InstagramCollectionRunItem,
                    InstagramCollectionRunItem.reel_id == InstagramReel.id,
                )
                .join(
                    InstagramCollectionRun,
                    InstagramCollectionRun.id == InstagramCollectionRunItem.run_id,
                )
                .where(
                    InstagramCollectionRun.account_id == account_id,
                    InstagramCollectionRunItem.outcome.in_(self._acquisition_outcomes()),
                    InstagramReel.pipeline_status.in_(self._durable_statuses()),
                    InstagramReel.source_object_key.is_not(None),
                    InstagramReel.source_sha256.is_not(None),
                    InstagramReel.source_byte_size.is_not(None),
                )
                .distinct()
                .order_by(InstagramReel.source_object_key)
            ).all()
        return tuple(
            DurableReelSnapshot(
                row.id, row.source_object_key, row.source_sha256, row.source_byte_size
            )
            for row in rows
        )

    def commit_available(self, run_id: UUID, candidate: ReelCandidate) -> None:
        with self._sessions.begin() as session:
            reel = self._reel(session, candidate.shortcode)
            if reel is None or reel.pipeline_status not in {
                ReelPipelineStatus.SOURCE_READY.value,
                ReelPipelineStatus.NORMALIZING.value,
                ReelPipelineStatus.READY.value,
            }:
                raise ValueError("Reel is no longer available.")
            self._add_item(session, run_id, reel, RunItemOutcome.ALREADY_AVAILABLE, None)

    def commit_source(
        self,
        run_id: UUID,
        candidate: ReelCandidate,
        source: ValidatedSource,
        object_key: str,
    ) -> None:
        with self._sessions.begin() as session:
            reel = self._reel(session, candidate.shortcode)
            now = datetime.now(UTC)
            if reel is None:
                reel = InstagramReel(
                    shortcode=candidate.shortcode,
                    canonical_url=candidate.canonical_url,
                    pipeline_status=ReelPipelineStatus.DISCOVERED.value,
                    discovered_at=now,
                )
                session.add(reel)
                session.flush()
            if reel.pipeline_status == ReelPipelineStatus.FAILED.value:
                require_transition(
                    REEL_PIPELINE_TRANSITIONS,
                    ReelPipelineStatus.FAILED,
                    ReelPipelineStatus.DOWNLOADING,
                )
                reel.pipeline_status = ReelPipelineStatus.DOWNLOADING.value
            elif reel.pipeline_status == ReelPipelineStatus.DISCOVERED.value:
                require_transition(
                    REEL_PIPELINE_TRANSITIONS,
                    ReelPipelineStatus.DISCOVERED,
                    ReelPipelineStatus.DOWNLOADING,
                )
                reel.pipeline_status = ReelPipelineStatus.DOWNLOADING.value
            elif reel.pipeline_status != ReelPipelineStatus.DOWNLOADING.value:
                raise ValueError("Reel is not eligible for source commit.")
            require_transition(
                REEL_PIPELINE_TRANSITIONS,
                ReelPipelineStatus.DOWNLOADING,
                ReelPipelineStatus.SOURCE_READY,
            )
            reel.pipeline_status = ReelPipelineStatus.SOURCE_READY.value
            reel.source_object_key = object_key
            reel.source_sha256 = source.sha256
            reel.source_byte_size = source.byte_size
            reel.source_ready_at = now
            reel.failure_reason_code = None
            session.add(
                InstagramNormalizationJob(
                    reel_id=reel.id,
                    status=NormalizationJobStatus.PENDING.value,
                    attempt_count=0,
                )
            )
            self._add_item(
                session,
                run_id,
                reel,
                RunItemOutcome.SOURCE_COMMITTED,
                DownloadAuthMode.SESSION_FIRST,
            )

    def record_failure(
        self,
        run_id: UUID,
        candidate: ReelCandidate,
        reason_code: str,
        *,
        download_attempted: bool,
    ) -> None:
        """Durably record a safe failure when its transaction can still be opened."""
        with self._sessions.begin() as session:
            reel = self._reel(session, candidate.shortcode)
            now = datetime.now(UTC)
            if reel is None:
                reel = InstagramReel(
                    shortcode=candidate.shortcode,
                    canonical_url=candidate.canonical_url,
                    pipeline_status=ReelPipelineStatus.DISCOVERED.value,
                    discovered_at=now,
                )
                session.add(reel)
                session.flush()
            if reel.pipeline_status in {
                ReelPipelineStatus.DISCOVERED.value,
                ReelPipelineStatus.DOWNLOADING.value,
            }:
                reel.pipeline_status = ReelPipelineStatus.FAILED.value
                reel.failed_at = now
                reel.failure_reason_code = reason_code
            self._add_item(
                session,
                run_id,
                reel,
                RunItemOutcome.FAILED,
                DownloadAuthMode.SESSION_FIRST if download_attempted else None,
                reason_code,
            )

    def fail_run(self, run_id: UUID, reason_code: str) -> None:
        with self._sessions.begin() as session:
            run = session.get(InstagramCollectionRun, run_id)
            if run is not None and run.status == CollectionRunStatus.RUNNING.value:
                run.status = CollectionRunStatus.FAILED.value
                run.stop_reason_code = reason_code
                run.completed_at = datetime.now(UTC)

    def cancel_run(self, run_id: UUID, reason_code: str) -> CancelRunOutcome:
        with self._sessions.begin() as session:
            run = session.get(InstagramCollectionRun, run_id)
            if run is None:
                return CancelRunOutcome.NOT_FOUND
            if run.status not in {
                CollectionRunStatus.QUEUED.value,
                CollectionRunStatus.RUNNING.value,
            }:
                return CancelRunOutcome.ALREADY_TERMINAL
            run.status = CollectionRunStatus.CANCELLED.value
            run.stop_reason_code = reason_code
            run.completed_at = datetime.now(UTC)
            return CancelRunOutcome.CANCELLED

    def complete_run(self, run_id: UUID) -> None:
        with self._sessions.begin() as session:
            run = session.get(InstagramCollectionRun, run_id)
            if run is not None:
                run.status = CollectionRunStatus.COMPLETED.value
                run.completed_at = datetime.now(UTC)

    def complete_if_account_durable_total(self, run_id: UUID, desired_total: int) -> bool:
        """Atomically recheck account ownership before declaring continuation success."""

        with self._sessions.begin() as session:
            run = session.get(InstagramCollectionRun, run_id)
            if run is None or run.status != CollectionRunStatus.RUNNING.value:
                return False
            if self._account_durable_count(session, run.account_id) != desired_total:
                return False
            run.status = CollectionRunStatus.COMPLETED.value
            run.completed_at = datetime.now(UTC)
            return True

    def summary(self, run_id: UUID) -> tuple[int, int, int, str]:
        with self._sessions() as session:
            run = session.get(InstagramCollectionRun, run_id)
            if run is None:
                raise LookupError("Collection run not found.")
            return (
                run.source_committed_count,
                run.already_available_count,
                run.failed_count,
                run.status,
            )

    @staticmethod
    def _reel(session: Session, shortcode: str) -> InstagramReel | None:
        return session.scalar(select(InstagramReel).where(InstagramReel.shortcode == shortcode))

    @staticmethod
    def _durable_statuses() -> tuple[str, ...]:
        return (
            ReelPipelineStatus.SOURCE_READY.value,
            ReelPipelineStatus.NORMALIZING.value,
            ReelPipelineStatus.READY.value,
        )

    @staticmethod
    def _acquisition_outcomes() -> tuple[str, ...]:
        return (RunItemOutcome.SOURCE_COMMITTED.value, RunItemOutcome.ALREADY_AVAILABLE.value)

    def _account_durable_count(self, session: Session, account_id: UUID) -> int:
        value = session.scalar(
            select(func.count(distinct(InstagramReel.id)))
            .select_from(InstagramReel)
            .join(
                InstagramCollectionRunItem, InstagramCollectionRunItem.reel_id == InstagramReel.id
            )
            .join(
                InstagramCollectionRun,
                InstagramCollectionRun.id == InstagramCollectionRunItem.run_id,
            )
            .where(
                InstagramCollectionRun.account_id == account_id,
                InstagramCollectionRunItem.outcome.in_(self._acquisition_outcomes()),
                InstagramReel.pipeline_status.in_(self._durable_statuses()),
                InstagramReel.source_object_key.is_not(None),
                InstagramReel.source_sha256.is_not(None),
                InstagramReel.source_byte_size.is_not(None),
            )
        )
        return int(value or 0)

    @staticmethod
    def _add_item(
        session: Session,
        run_id: UUID,
        reel: InstagramReel,
        outcome: RunItemOutcome,
        auth_mode: DownloadAuthMode | None,
        reason_code: str | None = None,
    ) -> None:
        run = session.get(InstagramCollectionRun, run_id)
        if run is None:
            raise LookupError("Collection run not found.")
        position = run.source_committed_count + run.already_available_count + run.failed_count + 1
        session.add(
            InstagramCollectionRunItem(
                run_id=run_id,
                reel_id=reel.id,
                position=position,
                outcome=outcome.value,
                download_auth_mode=None if auth_mode is None else auth_mode.value,
                reason_code=reason_code,
                completed_at=datetime.now(UTC),
            )
        )
        if outcome is RunItemOutcome.SOURCE_COMMITTED:
            run.source_committed_count += 1
        elif outcome is RunItemOutcome.ALREADY_AVAILABLE:
            run.already_available_count += 1
        else:
            run.failed_count += 1
