import shutil
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
    InstagramNormalizationJob,
    InstagramReel,
)
from app.instagram.collector.canonical import InvalidReelCandidate, validate_candidate
from app.instagram.collector.contracts import PublishedSource, ReelCandidate
from app.instagram.collector.fixtures import (
    FixtureDownloader,
    FixtureFeed,
    FixtureRollbackFailingPersistence,
    FixtureValidator,
    LocalFixtureSourceStorage,
)
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.collector.service import CollectorEngine, CollectorLimits
from app.instagram.contracts import CollectionTrigger, ReelPipelineStatus, RunItemOutcome


class Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def record(self, event: str) -> None:
        self.events.append(event)


@pytest.fixture
def setup(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'collector.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        account = InstagramAccount(id=uuid4(), status="connected", auto_collect_enabled=False)
        session.add(account)
    return sessions, account.id, tmp_path


def candidates(count: int = 3) -> list[ReelCandidate]:
    return [
        ReelCandidate(f"TEST_{index}", f"https://www.instagram.com/reel/TEST_{index}/")
        for index in range(count)
    ]


def make_engine(setup, *, downloader=None, validator=None, feed=None, recorder=None):
    sessions, _account_id, root = setup
    return CollectorEngine(
        CollectorPersistence(sessions),
        feed or FixtureFeed(candidates()),
        downloader or FixtureDownloader(),
        validator or FixtureValidator(),
        LocalFixtureSourceStorage(root / "sources"),
        limits=CollectorLimits(max_target=5, max_advances=5),
        recorder=recorder,
    )


def test_commit_before_advance_order_and_final_item_no_extra_advance(setup) -> None:
    sessions, account_id, _root = setup
    recorder = Recorder()
    summary = make_engine(setup, recorder=recorder).collect(account_id, CollectionTrigger.MANUAL, 2)
    assert summary.status == "completed"
    assert summary.source_committed_count == 2
    assert summary.confirmed_advances == 1
    assert recorder.events == [
        "detect",
        "pause",
        "download",
        "validation",
        "publication",
        "db_commit",
        "advance",
        "transition_confirmed",
        "detect",
        "pause",
        "download",
        "validation",
        "publication",
        "db_commit",
    ]
    with sessions() as session:
        assert len(session.scalars(select(InstagramNormalizationJob)).all()) == 2
        assert len(session.scalars(select(InstagramCollectionRunItem)).all()) == 2


@pytest.mark.parametrize("failure", ["download", "validation", "storage"])
def test_failures_do_not_advance_or_leave_temporary_files(setup, failure: str) -> None:
    sessions, account_id, root = setup
    downloader = FixtureDownloader(fail=failure == "download")
    validator = FixtureValidator(fail=failure == "validation")
    storage = LocalFixtureSourceStorage(root / "sources", fail_publish=failure == "storage")
    summary = CollectorEngine(
        CollectorPersistence(sessions), FixtureFeed(candidates()), downloader, validator, storage
    ).collect(account_id, CollectionTrigger.MANUAL, 2)
    assert summary.status == "failed"
    assert summary.confirmed_advances == 0
    assert summary.stop_reason_code in {
        "DOWNLOAD_FAILED",
        "VALIDATION_FAILED",
        "STORAGE_FAILED",
        "DATABASE_WRITE_FAILED",
    }
    temporary_dir = root / "sources" / ".temporary"
    assert not temporary_dir.exists() or not list(temporary_dir.glob("*.part"))


def test_available_reel_is_not_downloaded_and_uses_null_auth_mode(setup) -> None:
    sessions, account_id, root = setup
    candidate = candidates(1)[0]
    with sessions.begin() as session:
        session.add(
            InstagramReel(
                shortcode=candidate.shortcode,
                canonical_url=candidate.canonical_url,
                pipeline_status=ReelPipelineStatus.SOURCE_READY.value,
                source_object_key="instagram-sources/TEST_0.mp4",
                source_sha256="a" * 64,
                source_byte_size=1,
            )
        )
    summary = make_engine(
        setup,
        downloader=FixtureDownloader(fail=True),
        feed=FixtureFeed([candidate]),
    ).collect(
        account_id, CollectionTrigger.MANUAL, 1
    )
    assert summary.status == "completed"
    assert summary.already_available_count == 1
    with sessions() as session:
        assert session.scalar(select(InstagramCollectionRunItem.download_auth_mode)) is None
        assert not (root / "sources" / ".temporary").exists()


def test_duplicate_shortcode_and_transition_timeout_stop_without_loop(setup) -> None:
    _sessions, account_id, _root = setup
    duplicated = FixtureFeed([candidates(1)[0], candidates(1)[0]])
    summary = make_engine(setup, feed=duplicated).collect(account_id, CollectionTrigger.MANUAL, 2)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "TRANSITION_FAILED"
    timeout = make_engine(setup, feed=FixtureFeed(candidates(), transition_timeout=True)).collect(
        account_id, CollectionTrigger.MANUAL, 2
    )
    assert timeout.status == "failed"
    assert timeout.stop_reason_code == "TRANSITION_FAILED"
    assert timeout.confirmed_advances == 0


def test_repeated_shortcode_after_a_confirmed_advance_stops_without_a_second_item(setup) -> None:
    sessions, account_id, _root = setup
    feed = FixtureFeed([candidates(2)[0], candidates(2)[1], candidates(2)[0]])
    summary = make_engine(setup, feed=feed).collect(account_id, CollectionTrigger.MANUAL, 3)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "DUPLICATE_REEL"
    assert summary.confirmed_advances == 1
    with sessions() as session:
        assert len(session.scalars(select(InstagramCollectionRunItem)).all()) == 2


def test_target_limit_is_bounded(setup) -> None:
    _sessions, account_id, _root = setup
    with pytest.raises(ValueError):
        make_engine(setup).collect(account_id, CollectionTrigger.MANUAL, 6)


def test_fixture_storage_rejects_path_traversal(setup) -> None:
    _sessions, _account_id, root = setup
    storage = LocalFixtureSourceStorage(root / "sources")
    with pytest.raises(ValueError):
        storage.exists("../outside.mp4")


def test_successful_commit_writes_source_metadata_job_item_and_counter_together(setup) -> None:
    sessions, account_id, _root = setup
    summary = make_engine(setup, feed=FixtureFeed(candidates(1))).collect(
        account_id,
        CollectionTrigger.MANUAL,
        1,
    )
    assert summary.status == "completed"
    with sessions() as session:
        reel = session.scalar(select(InstagramReel))
        job = session.scalar(select(InstagramNormalizationJob))
        item = session.scalar(select(InstagramCollectionRunItem))
        assert reel is not None
        assert job is not None
        assert item is not None
        assert reel.pipeline_status == ReelPipelineStatus.SOURCE_READY.value
        assert reel.source_object_key == "instagram-sources/TEST_0.mp4"
        assert job.reel_id == reel.id
        assert item.outcome == "source_committed"
        assert item.download_auth_mode == "session_first"


def test_real_transaction_rollback_compensates_a_newly_published_object(setup) -> None:
    sessions, account_id, root = setup
    storage = LocalFixtureSourceStorage(root / "sources")
    summary = CollectorEngine(
        FixtureRollbackFailingPersistence(sessions),
        FixtureFeed(candidates(1)),
        FixtureDownloader(),
        FixtureValidator(),
        storage,
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "DATABASE_WRITE_FAILED"
    assert summary.confirmed_advances == 0
    assert not storage.exists("instagram-sources/TEST_0.mp4")
    with sessions() as session:
        reel = session.scalar(select(InstagramReel))
        run_item = session.scalar(
            select(InstagramCollectionRunItem).where(
                InstagramCollectionRunItem.outcome == RunItemOutcome.SOURCE_COMMITTED.value
            )
        )
        assert reel is not None
        assert reel.pipeline_status == ReelPipelineStatus.FAILED.value
        assert reel.source_object_key is None
        assert reel.source_sha256 is None
        assert reel.source_byte_size is None
        assert session.scalar(select(InstagramNormalizationJob)) is None
        assert run_item is None
        run = session.scalar(select(InstagramCollectionRun))
        assert run is not None
        assert run.source_committed_count == 0
        assert run.status == "failed"


def test_database_failure_never_deletes_an_existing_object(setup) -> None:
    sessions, account_id, root = setup
    storage = LocalFixtureSourceStorage(root / "sources")
    existing = root / "sources" / "instagram-sources" / "TEST_0.mp4"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"pre-existing")
    summary = CollectorEngine(
        FixtureRollbackFailingPersistence(sessions),
        FixtureFeed(candidates(1)),
        FixtureDownloader(),
        FixtureValidator(),
        storage,
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "failed"
    assert existing.read_bytes() == b"pre-existing"


def test_compensation_failure_keeps_primary_database_reason_safe(setup) -> None:
    sessions, account_id, root = setup
    storage = LocalFixtureSourceStorage(root / "sources", fail_delete=True)
    summary = CollectorEngine(
        FixtureRollbackFailingPersistence(sessions),
        FixtureFeed(candidates(1)),
        FixtureDownloader(),
        FixtureValidator(),
        storage,
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "DATABASE_WRITE_FAILED_COMPENSATION_FAILED"
    assert summary.confirmed_advances == 0
    assert storage.exists("instagram-sources/TEST_0.mp4")
    assert "fixture" not in str(summary)


def test_available_status_is_rechecked_inside_commit_transaction(setup) -> None:
    sessions, account_id, _root = setup
    candidate = candidates(1)[0]
    with sessions.begin() as session:
        session.add(
            InstagramReel(
                shortcode=candidate.shortcode,
                canonical_url=candidate.canonical_url,
                pipeline_status=ReelPipelineStatus.SOURCE_READY.value,
                source_object_key="instagram-sources/TEST_0.mp4",
                source_sha256="a" * 64,
                source_byte_size=1,
            )
        )
    persistence = _StatusChangingPersistence(CollectorPersistence(sessions), sessions)
    summary = CollectorEngine(
        persistence,
        FixtureFeed([candidate]),
        FixtureDownloader(),
        FixtureValidator(),
        LocalFixtureSourceStorage(_root / "sources"),
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "DATABASE_WRITE_FAILED"
    assert summary.confirmed_advances == 0
    with sessions() as session:
        assert session.scalar(select(InstagramCollectionRunItem)) is None


def test_copying_publish_still_cleans_the_collector_owned_temporary_file(setup) -> None:
    sessions, account_id, root = setup
    storage = _CopyingSourceStorage(root / "sources")
    summary = CollectorEngine(
        CollectorPersistence(sessions),
        FixtureFeed(candidates(1)),
        FixtureDownloader(),
        FixtureValidator(),
        storage,
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "completed"
    assert not list((root / "sources" / ".temporary").glob("*.part"))


def test_close_and_recorder_failures_do_not_replace_a_completed_summary(setup) -> None:
    _sessions, account_id, _root = setup
    summary = make_engine(
        setup,
        feed=_CloseFailingFeed(candidates(1)),
        recorder=_FailingRecorder(),
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "completed"
    assert summary.stop_reason_code is None


def test_close_and_fail_run_failures_do_not_replace_primary_safe_reason(setup) -> None:
    sessions, account_id, root = setup
    summary = CollectorEngine(
        _FailRunFailingPersistence(CollectorPersistence(sessions)),
        _CloseFailingFeed(candidates(1)),
        FixtureDownloader(fail=True),
        FixtureValidator(),
        LocalFixtureSourceStorage(root / "sources"),
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "DOWNLOAD_FAILED"
    assert "fixture download failure" not in str(summary)


def test_temporary_cleanup_failure_does_not_replace_primary_safe_reason(setup) -> None:
    sessions, account_id, root = setup
    summary = CollectorEngine(
        CollectorPersistence(sessions),
        FixtureFeed(candidates(1)),
        FixtureDownloader(fail=True),
        FixtureValidator(),
        _CleanupFailingStorage(root / "sources"),
    ).collect(account_id, CollectionTrigger.MANUAL, 1)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "DOWNLOAD_FAILED"


@pytest.mark.parametrize(
    "url",
    [
        "http://www.instagram.com/reel/SAFE_CODE/",
        "https://instagram.com/reel/SAFE_CODE/",
        "https://www.instagram.com/reel/SAFE_CODE/?query=1",
        "https://www.instagram.com/reel/SAFE_CODE/#fragment",
        "https://www.instagram.com/reel/not.valid/",
        "https://www.instagram.com/p/SAFE_CODE/",
        "https://www.instagram.com:abc/reel/SAFE_CODE/",
    ],
)
def test_canonical_reel_policy_rejects_noncanonical_urls(url: str) -> None:
    with pytest.raises(InvalidReelCandidate):
        validate_candidate(ReelCandidate("SAFE_CODE", url))


def test_canonical_reel_policy_enforces_shortcode_length_and_path_match() -> None:
    too_long = "A" * 65
    with pytest.raises(InvalidReelCandidate):
        validate_candidate(ReelCandidate(too_long, f"https://www.instagram.com/reel/{too_long}/"))
    with pytest.raises(InvalidReelCandidate):
        validate_candidate(ReelCandidate("SAFE_CODE", "https://www.instagram.com/reel/OTHER_CODE/"))


def test_invalid_transition_candidate_never_counts_as_confirmed_advance(setup) -> None:
    _sessions, account_id, _root = setup
    invalid = ReelCandidate("BAD.CODE", "https://www.instagram.com/reel/BAD.CODE/")
    summary = make_engine(
        setup,
        feed=FixtureFeed([candidates(1)[0], invalid]),
    ).collect(account_id, CollectionTrigger.MANUAL, 2)
    assert summary.status == "failed"
    assert summary.stop_reason_code == "INVALID_REEL_CANDIDATE"
    assert summary.confirmed_advances == 0


def test_invalid_initial_candidate_uses_only_the_safe_reason_code(setup) -> None:
    _sessions, account_id, _root = setup
    malformed = ReelCandidate("SAFE_CODE", "https://www.instagram.com:abc/reel/SAFE_CODE/")
    summary = make_engine(setup, feed=FixtureFeed([malformed])).collect(
        account_id,
        CollectionTrigger.MANUAL,
        1,
    )
    assert summary.status == "failed"
    assert summary.stop_reason_code == "INVALID_REEL_CANDIDATE"
    assert "abc" not in str(summary)


class _StatusChangingPersistence:
    def __init__(self, delegate: CollectorPersistence, sessions) -> None:
        self._delegate = delegate
        self._sessions = sessions

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def reel_status(self, shortcode: str) -> str | None:
        status = self._delegate.reel_status(shortcode)
        with self._sessions.begin() as session:
            reel = session.scalar(select(InstagramReel).where(InstagramReel.shortcode == shortcode))
            assert reel is not None
            reel.pipeline_status = ReelPipelineStatus.FAILED.value
        return status


class _CopyingSourceStorage(LocalFixtureSourceStorage):
    def publish(self, temporary_path: Path, object_key: str) -> PublishedSource:
        destination = self._resolve(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temporary_path, destination)
        return PublishedSource(object_key=object_key, created_by_attempt=True)


class _CleanupFailingStorage(LocalFixtureSourceStorage):
    def cleanup_temporary(self, temporary_path: Path) -> None:
        del temporary_path
        raise RuntimeError("untrusted cleanup error")


class _CloseFailingFeed(FixtureFeed):
    def close(self) -> None:
        raise RuntimeError("untrusted close error")


class _FailingRecorder:
    def record(self, event: str) -> None:
        del event
        raise RuntimeError("untrusted recorder error")


class _FailRunFailingPersistence:
    def __init__(self, delegate: CollectorPersistence) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def fail_run(self, run_id, reason_code: str) -> None:
        del run_id, reason_code
        raise RuntimeError("untrusted finalization error")
