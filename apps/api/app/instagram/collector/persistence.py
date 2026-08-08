"""SQLAlchemy transaction boundary for Collector source commits."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
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
            return session.scalar(
                select(InstagramCollectionRun.id).where(
                    InstagramCollectionRun.account_id == account_id,
                    InstagramCollectionRun.status.in_(
                        (CollectionRunStatus.QUEUED.value, CollectionRunStatus.RUNNING.value)
                    ),
                )
            ) is not None

    def reel_status(self, shortcode: str) -> str | None:
        with self._sessions() as session:
            statement = select(InstagramReel.pipeline_status).where(
                InstagramReel.shortcode == shortcode
            )
            return session.scalar(statement)

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
