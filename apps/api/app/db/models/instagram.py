"""Persistence foundation for the future server-side Instagram Collector."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.instagram.contracts import (
    AccountStatus,
    CollectionRunStatus,
    CollectionTrigger,
    DownloadAuthMode,
    NormalizationJobStatus,
    ReelPipelineStatus,
    RunItemOutcome,
)

ACCOUNT_STATUSES = tuple(status.value for status in AccountStatus)
COLLECTION_RUN_STATUSES = tuple(status.value for status in CollectionRunStatus)
COLLECTION_TRIGGERS = tuple(trigger.value for trigger in CollectionTrigger)
REEL_PIPELINE_STATUSES = tuple(status.value for status in ReelPipelineStatus)
NORMALIZATION_JOB_STATUSES = tuple(status.value for status in NormalizationJobStatus)
RUN_ITEM_OUTCOMES = tuple(outcome.value for outcome in RunItemOutcome)
DOWNLOAD_AUTH_MODES = tuple(mode.value for mode in DownloadAuthMode)
REASON_CODE_MAX_LENGTH = 64


def _enum_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class InstagramAccount(Base):
    __tablename__ = "instagram_accounts"
    __table_args__ = (
        _enum_check("status", ACCOUNT_STATUSES, "ck_instagram_accounts_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AccountStatus.DISCONNECTED.value
    )
    auto_collect_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reauth_required_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reason_code: Mapped[str | None] = mapped_column(String(REASON_CODE_MAX_LENGTH), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InstagramReel(Base):
    __tablename__ = "instagram_reels"
    __table_args__ = (
        _enum_check("pipeline_status", REEL_PIPELINE_STATUSES, "ck_instagram_reels_status"),
        CheckConstraint("length(trim(shortcode)) > 0", name="ck_reels_shortcode_nonempty"),
        CheckConstraint("length(trim(canonical_url)) > 0", name="ck_reels_canonical_url_nonempty"),
        CheckConstraint(
            "source_object_key IS NULL OR length(trim(source_object_key)) > 0",
            name="ck_reels_source_object_key_nonempty",
        ),
        CheckConstraint(
            "source_sha256 IS NULL OR length(source_sha256) = 64",
            name="ck_reels_source_sha256_length",
        ),
        CheckConstraint(
            "source_byte_size IS NULL OR source_byte_size > 0", name="ck_reels_size_positive"
        ),
        CheckConstraint(
            "pipeline_status NOT IN ('source_ready', 'normalizing', 'ready') "
            "OR (source_object_key IS NOT NULL AND source_sha256 IS NOT NULL "
            "AND source_byte_size IS NOT NULL AND source_byte_size > 0)",
            name="ck_reels_source_required",
        ),
        CheckConstraint(
            "pipeline_status <> 'ready' OR video_id IS NOT NULL",
            name="ck_reels_ready_requires_video",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    shortcode: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    canonical_url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    pipeline_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ReelPipelineStatus.DISCOVERED.value
    )
    source_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True, unique=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    video_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("videos.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    failure_reason_code: Mapped[str | None] = mapped_column(
        String(REASON_CODE_MAX_LENGTH), nullable=True
    )
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InstagramCollectionRun(Base):
    __tablename__ = "instagram_collection_runs"
    __table_args__ = (
        _enum_check("trigger", COLLECTION_TRIGGERS, "ck_collection_runs_trigger"),
        _enum_check("status", COLLECTION_RUN_STATUSES, "ck_collection_runs_status"),
        CheckConstraint("target_count > 0", name="ck_collection_runs_target_positive"),
        CheckConstraint(
            "source_committed_count >= 0 AND already_available_count >= 0 AND failed_count >= 0",
            name="ck_collection_runs_counters_nonnegative",
        ),
        CheckConstraint(
            "source_committed_count + already_available_count + failed_count <= target_count",
            name="ck_collection_runs_counters_within_target",
        ),
        Index(
            "uq_instagram_collection_runs_active_account",
            "account_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_committed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    already_available_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stop_reason_code: Mapped[str | None] = mapped_column(
        String(REASON_CODE_MAX_LENGTH), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InstagramCollectionRunItem(Base):
    __tablename__ = "instagram_collection_run_items"
    __table_args__ = (
        _enum_check("outcome", RUN_ITEM_OUTCOMES, "ck_collection_run_items_outcome"),
        _enum_check("download_auth_mode", DOWNLOAD_AUTH_MODES, "ck_collection_run_items_auth_mode"),
        CheckConstraint(
            "(outcome = 'source_committed' AND download_auth_mode IS NOT NULL) "
            "OR (outcome = 'already_available' AND download_auth_mode IS NULL) "
            "OR (outcome = 'failed' AND (download_auth_mode IS NULL "
            "OR download_auth_mode = 'session_first'))",
            name="ck_collection_run_items_auth_mode_outcome",
        ),
        CheckConstraint("position > 0", name="ck_collection_run_items_position_positive"),
        Index("uq_instagram_collection_run_items_run_position", "run_id", "position", unique=True),
        Index("uq_instagram_collection_run_items_run_reel", "run_id", "reel_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_collection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    reel_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_reels.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    download_auth_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(REASON_CODE_MAX_LENGTH), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InstagramNormalizationJob(Base):
    __tablename__ = "instagram_normalization_jobs"
    __table_args__ = (
        _enum_check("status", NORMALIZATION_JOB_STATUSES, "ck_normalization_jobs_status"),
        CheckConstraint("attempt_count >= 0", name="ck_normalization_jobs_attempt_nonnegative"),
        Index(
            "uq_instagram_normalization_jobs_active_reel",
            "reel_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    reel_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_reels.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason_code: Mapped[str | None] = mapped_column(String(REASON_CODE_MAX_LENGTH), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
