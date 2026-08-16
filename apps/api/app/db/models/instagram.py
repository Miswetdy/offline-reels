"""Persistence foundation for the future server-side Instagram Collector."""

# ruff: noqa: E501

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
    LoginSessionStatus,
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
LOGIN_SESSION_STATUSES = tuple(status.value for status in LoginSessionStatus)
REASON_CODE_MAX_LENGTH = 64


def _enum_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class InstagramAccount(Base):
    __tablename__ = "instagram_accounts"
    __table_args__ = (_enum_check("status", ACCOUNT_STATUSES, "ck_instagram_accounts_status"),)

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


class InstagramLoginSession(Base):
    """One short-lived remote-login grant. Browser state never enters this table."""

    __tablename__ = "instagram_login_sessions"
    __table_args__ = (
        _enum_check("status", LOGIN_SESSION_STATUSES, "ck_instagram_login_sessions_status"),
        CheckConstraint(
            "length(launch_token_hash) = 64", name="ck_login_session_token_hash_length"
        ),
        Index(
            "uq_instagram_login_sessions_active_account",
            "account_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'active')"),
            sqlite_where=text("status IN ('pending', 'active')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    prior_account_status: Mapped[str] = mapped_column(String(32), nullable=False)
    launch_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    reason_code: Mapped[str | None] = mapped_column(String(REASON_CODE_MAX_LENGTH), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    source_cleanup_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InstagramReelView(Base):
    """First confirmed view of one canonical Reel by one Instagram account.

    The video object is deliberately not owned by this table: the same
    canonical MP4 can remain available to another account after this account
    has consumed its Reel.
    """

    __tablename__ = "instagram_reel_views"
    __table_args__ = (
        Index("uq_instagram_reel_views_account_reel", "account_id", "reel_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False
    )
    reel_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_reels.id", ondelete="RESTRICT"), nullable=False
    )
    # Server time is canonical. This optional value is only a bounded audit
    # label generated by the PWA and is not a session, cookie, or identity.
    device_uuid: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
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
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    staging_prefix: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ManagementPairingChallenge(Base):
    __tablename__ = "management_pairing_challenges"
    __table_args__ = (
        CheckConstraint(
            "length(secret_hash) = 64", name="ck_management_pairing_secret_hash_length"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ManagementDeviceSession(Base):
    __tablename__ = "management_device_sessions"
    __table_args__ = (
        CheckConstraint(
            "length(session_token_hash) = 64", name="ck_management_session_hash_length"
        ),
        CheckConstraint("length(csrf_token_hash) = 64", name="ck_management_csrf_hash_length"),
        Index("ix_management_device_sessions_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, default=uuid4)
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ManagementIdempotencyRecord(Base):
    __tablename__ = "management_idempotency_records"
    __table_args__ = (
        CheckConstraint("length(key_hash) = 64", name="ck_management_idempotency_key_hash_length"),
        CheckConstraint(
            "length(request_fingerprint) = 64", name="ck_management_idempotency_fingerprint_length"
        ),
        Index(
            "uq_management_idempotency_scope",
            "session_id",
            "operation",
            "key_hash",
            unique=True,
        ),
        Index("ix_management_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("management_device_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[str] = mapped_column(String(2048), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InstagramCollectionSettings(Base):
    __tablename__ = "instagram_collection_settings"
    __table_args__ = (
        CheckConstraint(
            "target_reserve >= 1 AND target_reserve <= 10",
            name="ck_collection_settings_target_range",
        ),
    )

    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target_reserve: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ManagementReserveDevice(Base):
    """Last safe local-reserve snapshot for one account-owned browser device.

    This is intentionally not a mirror of IndexedDB or Cache Storage.  The
    browser remains authoritative for completed media; the control plane keeps
    only the values needed for an account-level, privacy-safe operator status.
    """

    __tablename__ = "management_reserve_devices"
    __table_args__ = (
        Index("uq_management_reserve_devices_account_device", "account_id", "device_uuid", unique=True),
        CheckConstraint("local_completed_count >= 0", name="ck_reserve_device_completed_nonnegative"),
        CheckConstraint("desired_count >= 1 AND desired_count <= 100", name="ck_reserve_device_desired_range"),
        CheckConstraint("low_watermark >= 0 AND low_watermark < desired_count", name="ck_reserve_device_watermark_range"),
        CheckConstraint("quota_threshold >= 50 AND quota_threshold <= 95", name="ck_reserve_device_quota_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False
    )
    # This UUID is generated once by the PWA and is neither a credential nor a
    # management-session identifier.
    device_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    auto_refill_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    local_completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    desired_count: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    low_watermark: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    quota_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ManagementRateLimit(Base):
    __tablename__ = "management_rate_limits"

    scope_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
