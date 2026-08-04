"""Side-effect-free state transition policy for the Collector domain."""

from collections.abc import Mapping
from enum import StrEnum

from app.instagram.contracts import (
    AccountStatus,
    CollectionRunStatus,
    NormalizationJobStatus,
    ReelPipelineStatus,
)


class InvalidStateTransition(ValueError):
    """Raised before a service attempts an illegal durable state change."""


ACCOUNT_TRANSITIONS: Mapping[AccountStatus, frozenset[AccountStatus]] = {
    AccountStatus.DISCONNECTED: frozenset({AccountStatus.CONNECTING}),
    AccountStatus.CONNECTING: frozenset(
        {
            AccountStatus.CONNECTED,
            AccountStatus.DISCONNECTED,
            AccountStatus.REAUTH_REQUIRED,
            AccountStatus.TEMPORARILY_LIMITED,
        }
    ),
    AccountStatus.CONNECTED: frozenset(
        {
            AccountStatus.DISCONNECTED,
            AccountStatus.REAUTH_REQUIRED,
            AccountStatus.TEMPORARILY_LIMITED,
        }
    ),
    AccountStatus.REAUTH_REQUIRED: frozenset(
        {AccountStatus.CONNECTING, AccountStatus.DISCONNECTED}
    ),
    AccountStatus.TEMPORARILY_LIMITED: frozenset(
        {AccountStatus.CONNECTING, AccountStatus.DISCONNECTED}
    ),
}

COLLECTION_RUN_TRANSITIONS: Mapping[CollectionRunStatus, frozenset[CollectionRunStatus]] = {
    CollectionRunStatus.QUEUED: frozenset(
        {
            CollectionRunStatus.RUNNING,
            CollectionRunStatus.CANCELLED,
            CollectionRunStatus.FAILED,
        }
    ),
    CollectionRunStatus.RUNNING: frozenset(
        {
            CollectionRunStatus.COMPLETED,
            CollectionRunStatus.CANCELLED,
            CollectionRunStatus.FAILED,
        }
    ),
    CollectionRunStatus.COMPLETED: frozenset(),
    CollectionRunStatus.CANCELLED: frozenset(),
    CollectionRunStatus.FAILED: frozenset(),
}

REEL_PIPELINE_TRANSITIONS: Mapping[ReelPipelineStatus, frozenset[ReelPipelineStatus]] = {
    ReelPipelineStatus.DISCOVERED: frozenset(
        {ReelPipelineStatus.DOWNLOADING, ReelPipelineStatus.FAILED}
    ),
    ReelPipelineStatus.DOWNLOADING: frozenset(
        {ReelPipelineStatus.SOURCE_READY, ReelPipelineStatus.FAILED}
    ),
    ReelPipelineStatus.SOURCE_READY: frozenset(
        {ReelPipelineStatus.NORMALIZING, ReelPipelineStatus.FAILED}
    ),
    ReelPipelineStatus.NORMALIZING: frozenset(
        {
            ReelPipelineStatus.SOURCE_READY,
            ReelPipelineStatus.READY,
            ReelPipelineStatus.FAILED,
        }
    ),
    ReelPipelineStatus.READY: frozenset(),
    ReelPipelineStatus.FAILED: frozenset({ReelPipelineStatus.DOWNLOADING}),
}

NORMALIZATION_JOB_TRANSITIONS: Mapping[
    NormalizationJobStatus, frozenset[NormalizationJobStatus]
] = {
    NormalizationJobStatus.PENDING: frozenset(
        {NormalizationJobStatus.RUNNING, NormalizationJobStatus.FAILED}
    ),
    NormalizationJobStatus.RUNNING: frozenset(
        {NormalizationJobStatus.COMPLETED, NormalizationJobStatus.FAILED}
    ),
    NormalizationJobStatus.COMPLETED: frozenset(),
    NormalizationJobStatus.FAILED: frozenset(),
}


def is_transition_allowed(
    policy: Mapping[StrEnum, frozenset[StrEnum]], current: StrEnum, target: StrEnum
) -> bool:
    """Return whether a non-noop domain transition is allowed by ``policy``."""

    return current is not target and target in policy[current]


def require_transition(
    policy: Mapping[StrEnum, frozenset[StrEnum]], current: StrEnum, target: StrEnum
) -> None:
    """Raise a safe error without embedding external/runtime details."""

    if not is_transition_allowed(policy, current, target):
        raise InvalidStateTransition(f"Transition {current} -> {target} is not allowed.")
