import pytest

from app.instagram.contracts import (
    AccountStatus,
    CollectionRunStatus,
    CollectionTrigger,
    DownloadAuthMode,
    LoginSessionStatus,
    NormalizationJobStatus,
    ReasonCode,
    ReelPipelineStatus,
    RunItemOutcome,
    is_valid_reason_code,
)
from app.instagram.transitions import (
    ACCOUNT_TRANSITIONS,
    COLLECTION_RUN_TRANSITIONS,
    NORMALIZATION_JOB_TRANSITIONS,
    REEL_PIPELINE_TRANSITIONS,
    InvalidStateTransition,
    is_transition_allowed,
    require_transition,
)


def test_collector_contract_values_are_explicit_and_stable() -> None:
    assert {status.value for status in AccountStatus} == {
        "disconnected",
        "connecting",
        "connected",
        "reauth_required",
        "temporarily_limited",
    }
    assert {status.value for status in CollectionRunStatus} == {
        "queued",
        "running",
        "completed",
        "cancelled",
        "failed",
    }
    assert {status.value for status in ReelPipelineStatus} == {
        "discovered",
        "downloading",
        "source_ready",
        "normalizing",
        "ready",
        "failed",
    }
    assert {status.value for status in NormalizationJobStatus} == {
        "pending",
        "running",
        "completed",
        "failed",
    }
    assert {trigger.value for trigger in CollectionTrigger} == {"manual", "automatic"}
    assert {outcome.value for outcome in RunItemOutcome} == {
        "source_committed",
        "already_available",
        "failed",
    }
    assert {mode.value for mode in DownloadAuthMode} == {"session_first"}
    assert {status.value for status in LoginSessionStatus} == {
        "pending", "active", "completed", "expired", "cancelled"
    }
    assert ReasonCode.AUTH_REQUIRED.value == "AUTH_REQUIRED"


def test_reel_pipeline_happy_path_retry_and_terminal_rules() -> None:
    path = (
        ReelPipelineStatus.DISCOVERED,
        ReelPipelineStatus.DOWNLOADING,
        ReelPipelineStatus.SOURCE_READY,
        ReelPipelineStatus.NORMALIZING,
        ReelPipelineStatus.READY,
    )
    assert all(
        is_transition_allowed(REEL_PIPELINE_TRANSITIONS, current, target)
        for current, target in zip(path, path[1:])
    )
    assert is_transition_allowed(
        REEL_PIPELINE_TRANSITIONS, ReelPipelineStatus.DOWNLOADING, ReelPipelineStatus.FAILED
    )
    assert is_transition_allowed(
        REEL_PIPELINE_TRANSITIONS, ReelPipelineStatus.FAILED, ReelPipelineStatus.DOWNLOADING
    )
    assert not is_transition_allowed(
        REEL_PIPELINE_TRANSITIONS, ReelPipelineStatus.FAILED, ReelPipelineStatus.NORMALIZING
    )
    assert not is_transition_allowed(
        REEL_PIPELINE_TRANSITIONS, ReelPipelineStatus.FAILED, ReelPipelineStatus.READY
    )
    assert is_transition_allowed(
        REEL_PIPELINE_TRANSITIONS,
        ReelPipelineStatus.NORMALIZING,
        ReelPipelineStatus.SOURCE_READY,
    )
    assert not is_transition_allowed(
        REEL_PIPELINE_TRANSITIONS, ReelPipelineStatus.READY, ReelPipelineStatus.DOWNLOADING
    )
    with pytest.raises(InvalidStateTransition):
        require_transition(
            REEL_PIPELINE_TRANSITIONS, ReelPipelineStatus.READY, ReelPipelineStatus.DOWNLOADING
        )


def test_run_account_and_job_recovery_transitions_are_explicit() -> None:
    assert is_transition_allowed(
        COLLECTION_RUN_TRANSITIONS, CollectionRunStatus.QUEUED, CollectionRunStatus.RUNNING
    )
    assert is_transition_allowed(
        COLLECTION_RUN_TRANSITIONS, CollectionRunStatus.RUNNING, CollectionRunStatus.COMPLETED
    )
    assert not is_transition_allowed(
        COLLECTION_RUN_TRANSITIONS, CollectionRunStatus.COMPLETED, CollectionRunStatus.RUNNING
    )

    assert is_transition_allowed(
        ACCOUNT_TRANSITIONS, AccountStatus.CONNECTED, AccountStatus.REAUTH_REQUIRED
    )
    assert is_transition_allowed(
        ACCOUNT_TRANSITIONS, AccountStatus.REAUTH_REQUIRED, AccountStatus.CONNECTING
    )
    assert is_transition_allowed(
        ACCOUNT_TRANSITIONS, AccountStatus.TEMPORARILY_LIMITED, AccountStatus.CONNECTING
    )
    assert not is_transition_allowed(
        ACCOUNT_TRANSITIONS, AccountStatus.REAUTH_REQUIRED, AccountStatus.CONNECTED
    )

    assert not is_transition_allowed(
        NORMALIZATION_JOB_TRANSITIONS,
        NormalizationJobStatus.COMPLETED,
        NormalizationJobStatus.RUNNING,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("DOWNLOAD_FAILED", True),
        ("A", True),
        ("a", False),
        ("ERROR WITH SPACE", False),
        ("COOKIE=VALUE", False),
        ("КОД", False),
        ("ÉCHEC", False),
        ("_LEADING", False),
        ("A" * 65, False),
    ],
)
def test_reason_codes_are_short_machine_codes_only(value: str | None, expected: bool) -> None:
    assert is_valid_reason_code(value) is expected
