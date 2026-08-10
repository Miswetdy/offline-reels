"""Stable, safe-to-persist Collector value contracts."""

import re
from enum import StrEnum


class AccountStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    REAUTH_REQUIRED = "reauth_required"
    TEMPORARILY_LIMITED = "temporarily_limited"


class LoginSessionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class CollectionRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CollectionTrigger(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class ReelPipelineStatus(StrEnum):
    DISCOVERED = "discovered"
    DOWNLOADING = "downloading"
    SOURCE_READY = "source_ready"
    NORMALIZING = "normalizing"
    READY = "ready"
    FAILED = "failed"


class NormalizationJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunItemOutcome(StrEnum):
    SOURCE_COMMITTED = "source_committed"
    ALREADY_AVAILABLE = "already_available"
    FAILED = "failed"


class DownloadAuthMode(StrEnum):
    SESSION_FIRST = "session_first"


class ReasonCode(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CHECKPOINT_REQUIRED = "CHECKPOINT_REQUIRED"
    TEMPORARILY_LIMITED = "TEMPORARILY_LIMITED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    NORMALIZATION_FAILED = "NORMALIZATION_FAILED"
    STORAGE_FAILED = "STORAGE_FAILED"
    CANCELLED_BY_USER = "CANCELLED_BY_USER"
    LOGIN_EXPIRED = "LOGIN_EXPIRED"
    LOGIN_CANCELLED = "LOGIN_CANCELLED"


REASON_CODE_MAX_LENGTH = 64
REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def is_valid_reason_code(value: str | None) -> bool:
    """Accept only compact machine codes, never exception or browser content."""

    if value is None:
        return True
    return REASON_CODE_PATTERN.fullmatch(value) is not None
