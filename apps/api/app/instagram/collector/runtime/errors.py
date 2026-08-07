"""Safe runtime failures with stable reason codes only."""

from enum import StrEnum


class RuntimeReasonCode(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CHECKPOINT_REQUIRED = "CHECKPOINT_REQUIRED"
    TEMPORARILY_LIMITED = "TEMPORARILY_LIMITED"
    ACTIVE_REEL_NOT_FOUND = "ACTIVE_REEL_NOT_FOUND"
    BROWSER_CLOSED = "BROWSER_CLOSED"
    TRANSITION_TIMEOUT = "TRANSITION_TIMEOUT"
    INVALID_REEL_CANDIDATE = "INVALID_REEL_CANDIDATE"
    PROFILE_IN_USE = "PROFILE_IN_USE"
    COLLECTOR_DISABLED = "COLLECTOR_DISABLED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    STORAGE_FAILED = "STORAGE_FAILED"


class CollectorRuntimeError(RuntimeError):
    def __init__(self, code: RuntimeReasonCode) -> None:
        self.code = code
        super().__init__(code.value)
