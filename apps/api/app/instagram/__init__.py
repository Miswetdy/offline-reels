"""Pure contracts for the future server-side Instagram Collector.

This package deliberately contains no browser, downloader, storage, or worker
runtime. Those integrations are introduced only behind these contracts later.
"""

from app.instagram.contracts import (
    AccountStatus,
    CollectionRunStatus,
    CollectionTrigger,
    DownloadAuthMode,
    NormalizationJobStatus,
    ReasonCode,
    ReelPipelineStatus,
    RunItemOutcome,
)
from app.instagram.transitions import is_transition_allowed, require_transition

__all__ = [
    "AccountStatus",
    "CollectionRunStatus",
    "CollectionTrigger",
    "DownloadAuthMode",
    "NormalizationJobStatus",
    "ReasonCode",
    "ReelPipelineStatus",
    "RunItemOutcome",
    "is_transition_allowed",
    "require_transition",
]
