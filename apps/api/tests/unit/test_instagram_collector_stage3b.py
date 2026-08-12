import types
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    InstagramCollectionRunItem,
    InstagramReel,
)
from app.instagram.collector.contracts import (
    CancelRunOutcome,
    ReelCandidate,
    ScrollTargetDiagnostics,
    TransitionSamplingDiagnostics,
)
from app.instagram.collector.fixtures import (
    FixtureFeed,
    FixtureValidator,
    LocalFixtureSourceStorage,
)
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.collector.runtime.downloader import FreshSessionFirstYtDlpDownloader
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.minio_storage import MinioCollectorSourceStorage
from app.instagram.collector.runtime.operator import SafeEventTranscript
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings
from app.instagram.collector.runtime.verification import (
    CollectorPostRunVerifier,
    RunBaseline,
    capture_run_baseline,
    validate_event_transcript,
)
from app.instagram.collector.service import CollectorEngine, CollectorLimits
from app.instagram.contracts import AccountStatus, CollectionTrigger


def _candidates() -> list[ReelCandidate]:
    return [
        ReelCandidate(code, f"https://www.instagram.com/reel/{code}/")
        for code in ("STAGE3B_ONE", "STAGE3B_TWO", "STAGE3B_THREE")
    ]


@pytest.fixture
def setup(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'stage3b.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    account_id = uuid4()
    with sessions.begin() as session:
        session.add(InstagramAccount(id=account_id, status=AccountStatus.CONNECTED.value))
    return sessions, account_id, tmp_path


def _collector(setup, downloader, feed=None, **limits):
    sessions, _account_id, root = setup
    return CollectorEngine(
        CollectorPersistence(sessions),
        feed or FixtureFeed(_candidates()),
        downloader,
        FixtureValidator(),
        LocalFixtureSourceStorage(root / "sources"),
        limits=CollectorLimits(max_target=3, max_advances=2, **limits),
    )


def test_three_session_first_attempts_commit_before_two_scrolls(setup) -> None:
    provider = _CookieProvider()
    downloader = FreshSessionFirstYtDlpDownloader(
        lambda: object(),
        maximum_bytes=1024,
        provider=provider,
        facade_factory=_Facade,
    )
    feed = _CountingFeed(_candidates())
    summary = _collector(setup, downloader, feed=feed).collect(
        setup[1], CollectionTrigger.MANUAL, 3
    )
    assert summary.status == "completed"
    assert summary.source_committed_count == 3
    assert summary.confirmed_advances == 2
    assert feed.advance_calls == 2
    assert provider.calls == 3
    assert all(jar.cleared for jar in provider.jars)


def test_claimed_management_run_is_completed_in_place(setup) -> None:
    sessions, account_id, _root = setup
    persistence = CollectorPersistence(sessions)
    with sessions.begin() as session:
        session.add(
            InstagramCollectionRun(
                account_id=account_id,
                trigger=CollectionTrigger.MANUAL.value,
                status="queued",
                target_count=3,
            )
        )
    claimed = persistence.claim_queued_run(account_id)
    assert claimed is not None

    summary = _collector(setup, _WritingDownloader()).collect(
        account_id,
        CollectionTrigger.MANUAL,
        3,
        claimed_run_id=claimed.id,
    )

    assert summary.run_id == claimed.id
    assert summary.status == "completed"
    with sessions() as session:
        runs = session.scalars(select(InstagramCollectionRun)).all()
    assert len(runs) == 1
    assert runs[0].status == "completed"


def test_safe_direct_download_failure_stops_before_validation_storage_commit_and_scroll(
    setup,
) -> None:
    class DirectAuthFailure:
        def download(self, candidate, temporary_path: Path) -> None:
            del candidate, temporary_path
            raise CollectorRuntimeError(RuntimeReasonCode.DIRECT_DOWNLOAD_AUTH_REQUIRED)

    feed = _CountingFeed(_candidates())
    summary = _collector(setup, DirectAuthFailure(), feed=feed).collect(
        setup[1], CollectionTrigger.MANUAL, 3
    )
    assert summary.status == "failed"
    assert summary.stop_reason_code == "DIRECT_DOWNLOAD_AUTH_REQUIRED"
    assert summary.source_committed_count == 0
    assert feed.advance_calls == 0
    with setup[0]() as session:
        item = session.scalars(select(InstagramCollectionRunItem)).one()
        assert item.reason_code == "DIRECT_DOWNLOAD_AUTH_REQUIRED"


def test_terminal_download_failure_does_not_block_next_explicit_run(setup) -> None:
    failed = _collector(setup, _FailAtDownloader(1)).collect(
        setup[1], CollectionTrigger.MANUAL, 3
    )
    assert failed.status == "failed"
    retry = _collector(setup, _WritingDownloader()).collect(
        setup[1], CollectionTrigger.MANUAL, 3
    )
    assert retry.status == "completed"
    assert retry.source_committed_count == 3


def test_transition_timeout_after_wheel_preserves_durable_first_reel(setup) -> None:
    feed = _CountingFeed(_candidates(), transition_timeout=True)
    summary = _collector(setup, _WritingDownloader(), feed=feed).collect(
        setup[1], CollectionTrigger.MANUAL, 3
    )
    assert summary.status == "failed"
    assert summary.stop_reason_code == "TRANSITION_FAILED"
    assert summary.source_committed_count == 1
    assert summary.confirmed_advances == 0
    assert feed.advance_calls == 2


def test_retry_scroll_confirms_second_transition_without_repeating_download_or_commit(
    setup,
) -> None:
    feed = _RetryFeed(_candidates(), outcomes=["STAGE3B_TWO", None, "STAGE3B_THREE"])
    downloader = _CountingDownloader()
    transcript = SafeEventTranscript()
    engine = CollectorEngine(
        CollectorPersistence(setup[0]),
        feed,
        downloader,
        FixtureValidator(),
        LocalFixtureSourceStorage(setup[2] / "retry-sources"),
        limits=CollectorLimits(
            max_target=3,
            max_advances=2,
            max_transition_operations=2,
            max_scroll_actions=4,
        ),
        recorder=transcript,
    )
    summary = engine.collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert summary.status == "completed"
    assert summary.source_committed_count == 3
    assert summary.confirmed_advances == 2
    assert downloader.calls == 3
    assert feed.advance_calls == 3
    assert engine.transition_diagnostics == [
        {
            "position": 1,
            "scroll_attempt_count": 1,
            "poll_count": 2,
            "unchanged_sample_count": 0,
            "missing_candidate_count": 0,
            "different_candidate_observed": True,
            "stable_sample_count": 2,
            "scroll_target_available": True,
            "scroll_target_in_viewport": True,
            "mouse_move_performed": True,
            "stop_reason_code": None,
        },
        {
            "position": 2,
            "scroll_attempt_count": 2,
            "poll_count": 3,
            "unchanged_sample_count": 1,
            "missing_candidate_count": 0,
            "different_candidate_observed": True,
            "stable_sample_count": 2,
            "scroll_target_available": True,
            "scroll_target_in_viewport": True,
            "mouse_move_performed": True,
            "stop_reason_code": None,
        },
    ]
    assert [item["event"] for item in transcript.events if item["position"] == 2] == [
        "detect", "pause", "download", "validation", "publish", "db_commit",
        "advance", "advance_retry", "transition_confirmed",
    ]


def test_two_transitions_allow_at_most_four_wheels_and_never_scroll_the_third_reel(setup) -> None:
    feed = _RetryFeed(_candidates(), outcomes=[None, "STAGE3B_TWO", None, "STAGE3B_THREE"])
    summary = _collector(
        setup,
        _WritingDownloader(),
        feed=feed,
        max_transition_operations=2,
        max_scroll_actions=4,
    ).collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert summary.status == "completed"
    assert feed.advance_calls == 4


def test_verifier_accepts_retry_transcript_and_rejects_a_third_wheel() -> None:
    retry = [
        *[{"position": 1, "event": event} for event in (
            "detect", "pause", "download", "validation", "publish", "db_commit",
            "cooldown", "advance", "advance_retry", "transition_confirmed",
        )],
        *[{"position": 2, "event": event} for event in (
            "detect", "pause", "download", "validation", "publish", "db_commit",
            "cooldown", "advance", "transition_confirmed",
        )],
        *[{"position": 3, "event": event} for event in (
            "detect", "pause", "download", "validation", "publish", "db_commit",
        )],
    ]
    assert validate_event_transcript(retry, status="completed", target_count=3)
    third_wheel = [*retry]
    third_wheel.insert(9, {"position": 1, "event": "advance_retry"})
    assert not validate_event_transcript(third_wheel, status="completed", target_count=3)


def test_structured_transcript_proves_per_position_order(setup) -> None:
    transcript = SafeEventTranscript()
    engine = CollectorEngine(
        CollectorPersistence(setup[0]),
        FixtureFeed(_candidates()),
        _WritingDownloader(),
        FixtureValidator(),
        LocalFixtureSourceStorage(setup[2] / "structured-sources"),
        limits=CollectorLimits(max_target=3, max_advances=2, cooldown_seconds=0.001),
        recorder=transcript,
        sleep=lambda _seconds: None,
    )
    summary = engine.collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert summary.status == "completed"
    by_position = {
        position: [item["event"] for item in transcript.events if item["position"] == position]
        for position in (1, 2, 3)
    }
    assert by_position[1] == [
        "detect", "pause", "download", "validation", "publish", "db_commit",
        "cooldown", "advance", "transition_confirmed",
    ]
    assert by_position[2] == by_position[1]
    assert by_position[3] == [
        "detect", "pause", "download", "validation", "publish", "db_commit"
    ]


@pytest.mark.parametrize("failure_position", [1, 2, 3])
def test_failure_never_advances_the_current_reel(setup, failure_position: int) -> None:
    feed = _CountingFeed(_candidates())
    summary = _collector(setup, _FailAtDownloader(failure_position), feed=feed).collect(
        setup[1], CollectionTrigger.MANUAL, 3
    )
    assert summary.status == "failed"
    assert feed.advance_calls == failure_position - 1


def test_failure_and_cancellation_transcripts_never_advance_uncommitted_positions(setup) -> None:
    failed_events = SafeEventTranscript()
    failed_feed = _CountingFeed(_candidates())
    failed = CollectorEngine(
        CollectorPersistence(setup[0]),
        failed_feed,
        _FailAtDownloader(2),
        FixtureValidator(),
        LocalFixtureSourceStorage(setup[2] / "failed-transcript"),
        limits=CollectorLimits(max_target=3, max_advances=2, cooldown_seconds=0.001),
        recorder=failed_events,
        sleep=lambda _seconds: None,
    ).collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert failed.status == "failed"
    assert validate_event_transcript(failed_events.events, status="failed", target_count=3)
    assert not any(
        item == {"position": 2, "event": "advance"} for item in failed_events.events
    )
    cancel_account = uuid4()
    with setup[0].begin() as session:
        session.add(InstagramAccount(id=cancel_account, status=AccountStatus.CONNECTED.value))
    cancelled_events = SafeEventTranscript()
    cancel_candidates = [
        ReelCandidate(code, f"https://www.instagram.com/reel/{code}/")
        for code in ("CANCEL_ONE", "CANCEL_TWO", "CANCEL_THREE")
    ]
    cancelled = CollectorEngine(
        CollectorPersistence(setup[0]),
        _CancellingFeed(cancel_candidates),
        _WritingDownloader(),
        FixtureValidator(),
        LocalFixtureSourceStorage(setup[2] / "cancelled-transcript"),
        limits=CollectorLimits(max_target=3, max_advances=2, cooldown_seconds=0.001),
        recorder=cancelled_events,
        sleep=lambda _seconds: None,
    ).collect(cancel_account, CollectionTrigger.MANUAL, 3)
    assert cancelled.status == "cancelled"
    assert validate_event_transcript(cancelled_events.events, status="cancelled", target_count=3)


def test_cancellation_preserves_committed_source_and_marks_run_cancelled(setup) -> None:
    feed = _CancellingFeed(_candidates())
    summary = _collector(setup, _WritingDownloader(), feed=feed).collect(
        setup[1], CollectionTrigger.MANUAL, 3
    )
    assert summary.status == "cancelled"
    assert summary.source_committed_count == 1
    with setup[0]() as session:
        run = session.get(InstagramCollectionRun, summary.run_id)
        assert run is not None and run.stop_reason_code == "CANCELLED_BY_USER"
        assert len(session.scalars(select(InstagramReel)).all()) == 1


def test_run_byte_limit_blocks_publication_and_scroll(setup) -> None:
    feed = _CountingFeed(_candidates())
    summary = _collector(
        setup,
        _WritingDownloader(),
        feed=feed,
        max_run_bytes=1,
    ).collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "RUN_BYTE_LIMIT_EXCEEDED"
    assert feed.advance_calls == 0


def test_deadline_after_durable_commit_preserves_source_and_forbids_scroll(setup) -> None:
    now = [0.0]
    feed = _CountingFeed(_candidates())
    persistence = _DeadlineAfterCommitPersistence(setup[0], now)
    engine = CollectorEngine(
        persistence,
        feed,
        _WritingDownloader(),
        FixtureValidator(),
        LocalFixtureSourceStorage(setup[2] / "deadline-sources"),
        limits=CollectorLimits(max_target=3, max_advances=2, deadline_seconds=1.0),
        clock=lambda: now[0],
    )
    summary = engine.collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "TOTAL_TIMEOUT_REACHED"
    assert summary.source_committed_count == 1
    assert feed.advance_calls == 0
    assert (setup[2] / "deadline-sources" / "instagram-sources" / "STAGE3B_ONE.mp4").exists()


def test_deadline_after_publication_compensates_and_forbids_commit_or_scroll(setup) -> None:
    now = [0.0]
    feed = _CountingFeed(_candidates())
    storage = _DeadlineStorage(setup[2] / "deadline-compensation", now)
    engine = CollectorEngine(
        CollectorPersistence(setup[0]),
        feed,
        _WritingDownloader(),
        FixtureValidator(),
        storage,
        limits=CollectorLimits(max_target=3, max_advances=2, deadline_seconds=1.0),
        clock=lambda: now[0],
    )
    summary = engine.collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert summary.stop_reason_code == "TOTAL_TIMEOUT_REACHED"
    assert summary.source_committed_count == 0
    assert feed.advance_calls == 0
    assert storage.deleted == ["instagram-sources/STAGE3B_ONE.mp4"]


@pytest.mark.parametrize(
    ("boundary", "expected_committed", "expected_scrolls"),
    [
        ("before-download", 0, 0),
        ("after-download", 0, 0),
        ("after-validation", 0, 0),
        ("before-publication", 0, 0),
        ("after-publication", 0, 0),
        ("after-db-commit", 1, 0),
        ("before-cooldown", 1, 0),
        ("before-scroll", 1, 0),
        ("during-transition", 1, 1),
    ],
)
def test_cooperative_deadline_at_every_runtime_boundary(
    setup, boundary: str, expected_committed: int, expected_scrolls: int
) -> None:
    now = [0.0]
    feed = _BoundaryFeed(_candidates(), now, boundary)
    persistence = _BoundaryPersistence(setup[0], now, boundary)
    downloader = _BoundaryDownloader(now, boundary)
    validator = _BoundaryValidator(now, boundary)
    storage = _BoundaryStorage(setup[2] / f"boundary-{boundary}", now, boundary)

    def sleep(_seconds: float) -> None:
        if boundary == "before-scroll":
            now[0] = 2.0

    summary = CollectorEngine(
        persistence,
        feed,
        downloader,
        validator,
        storage,
        limits=CollectorLimits(
            max_target=3,
            max_advances=2,
            cooldown_seconds=0.01,
            deadline_seconds=1.0,
        ),
        clock=lambda: now[0],
        sleep=sleep,
    ).collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert summary.stop_reason_code == "TOTAL_TIMEOUT_REACHED"
    assert summary.source_committed_count == expected_committed
    assert feed.advance_calls == expected_scrolls
    if boundary == "after-publication":
        assert storage.deleted == ["instagram-sources/STAGE3B_ONE.mp4"]


def test_storage_object_conflict_is_safe_and_forbids_db_commit_and_scroll(setup) -> None:
    feed = _CountingFeed(_candidates())
    summary = CollectorEngine(
        CollectorPersistence(setup[0]),
        feed,
        _WritingDownloader(),
        FixtureValidator(),
        _ConflictStorage(setup[2] / "conflict"),
        limits=CollectorLimits(max_target=3, max_advances=2),
    ).collect(setup[1], CollectionTrigger.MANUAL, 3)
    assert summary.stop_reason_code == "STORAGE_OBJECT_CONFLICT"
    assert summary.source_committed_count == 0
    assert feed.advance_calls == 0


def test_account_lifecycle_and_active_run_guard(setup) -> None:
    persistence = CollectorPersistence(setup[0])
    account_id = setup[1]
    persistence.set_account_status(account_id, AccountStatus.REAUTH_REQUIRED, "AUTH_REQUIRED")
    assert persistence.account_status(account_id) is AccountStatus.REAUTH_REQUIRED
    persistence.set_account_status(account_id, AccountStatus.CONNECTING)
    persistence.set_account_status(account_id, AccountStatus.CONNECTED)
    persistence.create_run(account_id, CollectionTrigger.MANUAL, 3)
    assert persistence.active_run_exists(account_id)


def test_cancel_run_distinguishes_cancelled_not_found_and_terminal(setup) -> None:
    persistence = CollectorPersistence(setup[0])
    run_id = persistence.create_run(setup[1], CollectionTrigger.MANUAL, 3)
    assert persistence.cancel_run(run_id, "CANCELLED_BY_USER") is CancelRunOutcome.CANCELLED
    assert persistence.cancel_run(run_id, "CANCELLED_BY_USER") is CancelRunOutcome.ALREADY_TERMINAL
    assert persistence.cancel_run(uuid4(), "CANCELLED_BY_USER") is CancelRunOutcome.NOT_FOUND


def test_verifier_uses_pre_run_baseline_exact_delta_and_workspace_cleanliness(setup) -> None:
    sessions, account_id, root = setup
    client = _MemoryMinio()
    baseline = capture_run_baseline(sessions, client, "bucket")
    transcript = SafeEventTranscript()
    workspace = root / "verify-workspace"
    engine = CollectorEngine(
        CollectorPersistence(sessions),
        FixtureFeed(_candidates()),
        _WritingDownloader(),
        FixtureValidator(),
        MinioCollectorSourceStorage(client, "bucket", workspace, 1024),
        limits=CollectorLimits(max_target=3, max_advances=2, cooldown_seconds=0.001),
        recorder=transcript,
        sleep=lambda _seconds: None,
    )
    summary = engine.collect(account_id, CollectionTrigger.MANUAL, 3)
    assert summary.run_id is not None
    verified = CollectorPostRunVerifier(sessions, client, "bucket").verify(
        summary.run_id,
        baseline=baseline,
        transcript=transcript.events,
        workspace_root=workspace,
    )
    assert verified.verified
    client.objects["instagram-sources/unexpected.part"] = b"staging"
    rejected = CollectorPostRunVerifier(sessions, client, "bucket").verify(
        summary.run_id,
        baseline=baseline,
        transcript=transcript.events,
        workspace_root=workspace,
    )
    assert not rejected.verified
    assert not rejected.object_set_unchanged_except_expected
    client.objects.pop("instagram-sources/unexpected.part")
    partial = workspace / "temporary" / "leftover.part"
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_bytes(b"partial")
    rejected_workspace = CollectorPostRunVerifier(sessions, client, "bucket").verify(
        summary.run_id,
        baseline=baseline,
        transcript=transcript.events,
        workspace_root=workspace,
    )
    assert not rejected_workspace.verified
    assert not rejected_workspace.workspace_clean


def test_baseline_parser_rejects_missing_or_malformed_payload() -> None:
    assert RunBaseline.from_safe_dict(None) is None
    assert RunBaseline.from_safe_dict({"video_count": 0}) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_runtime_settings_reject_nonfinite_or_negative_operator_limits(
    tmp_path: Path,
    value: float,
) -> None:
    settings = CollectorRuntimeSettings(
        True,
        tmp_path / "profiles",
        tmp_path / "workspace",
        operator_deadline_seconds=value,
    )
    with pytest.raises(CollectorRuntimeError):
        settings.require_live(repository_root=tmp_path / "repository")


class _Jar:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


class _CookieProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.jars: list[_Jar] = []

    def get(self, context: object) -> _Jar:
        del context
        self.calls += 1
        jar = _Jar()
        self.jars.append(jar)
        return jar


class _Facade:
    def download(self, candidate, cookie_jar, temporary_path: Path, maximum_bytes: int) -> None:
        del candidate, cookie_jar, maximum_bytes
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(b"stage-3b-fixture")


class _WritingDownloader:
    def download(self, candidate, temporary_path: Path) -> None:
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(candidate.shortcode.encode())


class _CountingDownloader(_WritingDownloader):
    def __init__(self) -> None:
        self.calls = 0

    def download(self, candidate, temporary_path: Path) -> None:
        self.calls += 1
        super().download(candidate, temporary_path)


class _FailAtDownloader(_WritingDownloader):
    def __init__(self, position: int) -> None:
        self._position = position
        self._calls = 0

    def download(self, candidate, temporary_path: Path) -> None:
        self._calls += 1
        if self._calls == self._position:
            raise RuntimeError("sensitive failure")
        super().download(candidate, temporary_path)


class _CountingFeed(FixtureFeed):
    def __init__(
        self, candidates: list[ReelCandidate], *, transition_timeout: bool = False
    ) -> None:
        super().__init__(candidates, transition_timeout=transition_timeout)
        self.advance_calls = 0

    def advance(self) -> None:
        self.advance_calls += 1
        self._scroll_target_diagnostics = ScrollTargetDiagnostics(True, True, True)
        super().advance()


class _RetryFeed(_CountingFeed):
    """A fixture transition plan: None times out; a shortcode confirms next Reel."""

    def __init__(self, candidates: list[ReelCandidate], *, outcomes: list[str | None]) -> None:
        super().__init__(candidates)
        self._outcomes = list(outcomes)
        self._by_shortcode = {
            candidate.shortcode: index for index, candidate in enumerate(candidates)
        }

    def advance(self) -> None:
        self.advance_calls += 1
        self._scroll_target_diagnostics = ScrollTargetDiagnostics(True, True, True)

    def wait_for_next(self, previous_shortcode: str, should_stop=None):
        del previous_shortcode
        if should_stop is not None and should_stop():
            self._transition_diagnostics = TransitionSamplingDiagnostics(
                poll_count=1,
                stop_reason_code="TOTAL_TIMEOUT_REACHED",
            )
            return None
        outcome = self._outcomes.pop(0)
        if outcome is None:
            self._transition_diagnostics = TransitionSamplingDiagnostics(
                poll_count=1,
                unchanged_sample_count=1,
                stop_reason_code="TRANSITION_TIMEOUT",
            )
            return None
        self._index = self._by_shortcode[outcome]
        self._transition_diagnostics = TransitionSamplingDiagnostics(
            poll_count=2,
            different_candidate_observed=True,
            stable_sample_count=2,
        )
        return self.current()


class _CancellingFeed(_CountingFeed):
    def wait_for_next(self, previous_shortcode: str, should_stop=None):
        del previous_shortcode, should_stop
        raise KeyboardInterrupt


class _DeadlineAfterCommitPersistence(CollectorPersistence):
    def __init__(self, sessions, now: list[float]) -> None:
        super().__init__(sessions)
        self._now = now

    def commit_source(self, *args, **kwargs) -> None:
        super().commit_source(*args, **kwargs)
        self._now[0] = 2.0


class _DeadlineStorage(LocalFixtureSourceStorage):
    def __init__(self, root: Path, now: list[float]) -> None:
        super().__init__(root)
        self._now = now
        self.deleted: list[str] = []

    def publish(self, temporary_path: Path, object_key: str):
        published = super().publish(temporary_path, object_key)
        self._now[0] = 2.0
        return published

    def delete(self, object_key: str) -> None:
        self.deleted.append(object_key)
        super().delete(object_key)


class _ConflictStorage(LocalFixtureSourceStorage):
    def publish(self, temporary_path: Path, object_key: str):
        del temporary_path, object_key
        from app.instagram.collector.runtime.errors import RuntimeReasonCode

        raise CollectorRuntimeError(RuntimeReasonCode.STORAGE_OBJECT_CONFLICT)


class _BoundaryFeed(_CountingFeed):
    def __init__(self, candidates, now: list[float], boundary: str) -> None:
        super().__init__(candidates)
        self._now = now
        self._boundary = boundary

    def pause_current(self) -> None:
        if self._boundary == "before-download":
            self._now[0] = 2.0

    def wait_for_next(self, previous_shortcode: str, should_stop=None):
        if self._boundary == "during-transition":
            self._now[0] = 2.0
        return super().wait_for_next(previous_shortcode, should_stop)


class _BoundaryDownloader(_WritingDownloader):
    def __init__(self, now: list[float], boundary: str) -> None:
        self._now = now
        self._boundary = boundary

    def download(self, candidate, temporary_path: Path) -> None:
        super().download(candidate, temporary_path)
        if self._boundary == "after-download":
            self._now[0] = 2.0


class _BoundaryValidator(FixtureValidator):
    def __init__(self, now: list[float], boundary: str) -> None:
        super().__init__()
        self._now = now
        self._boundary = boundary

    def validate(self, temporary_path: Path):
        result = super().validate(temporary_path)
        if self._boundary in {"after-validation", "before-publication"}:
            self._now[0] = 2.0
        return result


class _BoundaryStorage(_DeadlineStorage):
    def __init__(self, root: Path, now: list[float], boundary: str) -> None:
        LocalFixtureSourceStorage.__init__(self, root)
        self._now = now
        self._boundary = boundary
        self.deleted = []

    def publish(self, temporary_path: Path, object_key: str):
        published = LocalFixtureSourceStorage.publish(self, temporary_path, object_key)
        if self._boundary == "after-publication":
            self._now[0] = 2.0
        return published


class _BoundaryPersistence(CollectorPersistence):
    def __init__(self, sessions, now: list[float], boundary: str) -> None:
        super().__init__(sessions)
        self._now = now
        self._boundary = boundary

    def commit_source(self, *args, **kwargs) -> None:
        super().commit_source(*args, **kwargs)
        if self._boundary in {"after-db-commit", "before-cooldown"}:
            self._now[0] = 2.0


class _MissingObject(Exception):
    code = "NoSuchKey"


class _Response(BytesIO):
    def release_conn(self) -> None:
        return None


class _MemoryMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def list_objects(self, bucket_name: str, *, prefix: str, recursive: bool):
        del bucket_name, recursive
        return [
            types.SimpleNamespace(object_name=key)
            for key in self.objects
            if key.startswith(prefix)
        ]

    def stat_object(self, bucket_name: str, object_name: str):
        del bucket_name
        if object_name not in self.objects:
            raise _MissingObject()
        return types.SimpleNamespace(size=len(self.objects[object_name]), content_type="video/mp4")

    def get_object(self, bucket_name: str, object_name: str):
        del bucket_name
        return _Response(self.objects[object_name])

    def fput_object(self, bucket_name: str, object_name: str, file_path: str, *, content_type: str):
        del bucket_name, content_type
        self.objects[object_name] = Path(file_path).read_bytes()

    def remove_object(self, bucket_name: str, object_name: str):
        del bucket_name
        self.objects.pop(object_name, None)
