"""Stage 3C.1 account-owned continuation semantics (network-free)."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.instagram import InstagramAccount, InstagramCollectionRunItem, InstagramReel
from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.fixtures import (
    FixtureDownloader,
    FixtureFeed,
    FixtureValidator,
    LocalFixtureSourceStorage,
)
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.operator import SafeEventTranscript
from app.instagram.collector.runtime.verification import validate_stage3c1_transcript
from app.instagram.collector.service import CollectorEngine, CollectorLimits
from app.instagram.contracts import CollectionTrigger, ReelPipelineStatus, RunItemOutcome


def _candidate(shortcode: str) -> ReelCandidate:
    return ReelCandidate(shortcode, f"https://www.instagram.com/reel/{shortcode}/")


def _engine(sessions, root: Path, feed, downloader, recorder=None) -> CollectorEngine:
    return CollectorEngine(
        CollectorPersistence(sessions),
        feed,
        downloader,
        FixtureValidator(),
        LocalFixtureSourceStorage(root / "sources"),
        limits=CollectorLimits(
            max_target=10,
            max_advances=29,
            max_transition_operations=29,
            max_scroll_actions=58,
            max_observations=30,
            cooldown_seconds=0.0,
        ),
        recorder=recorder,
        sleep=lambda _seconds: None,
    )


class _CountingDownloader(FixtureDownloader):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def download(self, candidate, temporary_path) -> None:
        self.calls += 1
        super().download(candidate, temporary_path)


class _BrowserClosingFeed(FixtureFeed):
    def pause_current(self) -> None:
        raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED)


def test_continuation_counts_account_history_not_global_reel_and_skips_duplicates(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'collector.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    account_id, other_account = uuid4(), uuid4()
    with sessions.begin() as session:
        session.add_all(
            [
                InstagramAccount(id=account_id, status="connected"),
                InstagramAccount(id=other_account, status="connected"),
            ]
        )
    first_three = [_candidate(f"OLD_{index}") for index in range(3)]
    assert (
        _engine(sessions, tmp_path, FixtureFeed(first_three), FixtureDownloader())
        .collect(account_id, CollectionTrigger.MANUAL, 3)
        .status
        == "completed"
    )
    global_reel = _candidate("GLOBAL_AVAILABLE")
    assert (
        _engine(sessions, tmp_path, FixtureFeed([global_reel]), FixtureDownloader())
        .collect(other_account, CollectionTrigger.MANUAL, 1)
        .status
        == "completed"
    )
    additions = [_candidate(f"NEW_{index}") for index in range(6)]
    downloader, transcript = _CountingDownloader(), SafeEventTranscript()
    summary = _engine(
        sessions,
        tmp_path,
        FixtureFeed([first_three[0], global_reel, first_three[1], *additions]),
        downloader,
        transcript,
    ).collect(account_id, CollectionTrigger.MANUAL, 7, desired_account_total=10)

    assert summary.status == "completed"
    assert summary.source_committed_count == 6
    assert summary.already_available_count == 1
    assert summary.duplicate_skipped_count == 2
    assert summary.observations == 9
    assert downloader.calls == 6  # Neither owned duplicates nor global availability downloads.
    assert CollectorPersistence(sessions).account_durable_count(account_id) == 10
    last_events = [event["event"] for event in transcript.events if event["position"] == 9]
    assert "advance" not in last_events and "cooldown" not in last_events
    with sessions() as session:
        items = session.scalars(
            select(InstagramCollectionRunItem).where(
                InstagramCollectionRunItem.run_id == summary.run_id
            )
        ).all()
        assert len(items) == 7
        assert {item.outcome for item in items} == {
            RunItemOutcome.SOURCE_COMMITTED.value,
            RunItemOutcome.ALREADY_AVAILABLE.value,
        }


def test_account_durable_count_requires_durable_metadata_and_historical_acquisition(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'collector.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    account_id = uuid4()
    with sessions.begin() as session:
        session.add(InstagramAccount(id=account_id, status="connected"))
        session.add(
            InstagramReel(
                shortcode="GLOBAL",
                canonical_url="https://www.instagram.com/reel/GLOBAL/",
                pipeline_status=ReelPipelineStatus.SOURCE_READY.value,
                source_object_key="instagram-sources/GLOBAL.mp4",
                source_sha256="a" * 64,
                source_byte_size=1,
            )
        )
    persistence = CollectorPersistence(sessions)
    assert persistence.account_durable_count(account_id) == 0
    assert not persistence.account_has_durable_reel(account_id, "GLOBAL")


def test_browser_closure_cancels_run_without_scroll_or_download(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'collector.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    account_id = uuid4()
    with sessions.begin() as session:
        session.add(InstagramAccount(id=account_id, status="connected"))
    downloader = _CountingDownloader()
    summary = _engine(
        sessions, tmp_path, _BrowserClosingFeed([_candidate("CLOSED")]), downloader
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "cancelled"
    assert summary.stop_reason_code == "BROWSER_CLOSED"
    assert downloader.calls == 0


def test_stage3c1_transcript_accepts_normal_transition_without_retry() -> None:
    events = [
        {"position": 1, "event": event}
        for event in (
            "detect", "pause", "download", "validation", "publish", "db_commit", "cooldown",
            "advance", "transition_confirmed",
        )
    ]
    events.extend(
        {"position": 2, "event": event}
        for event in ("detect", "pause", "download", "validation", "publish", "db_commit")
    )
    assert validate_stage3c1_transcript(events, status="completed", final_position=2)
