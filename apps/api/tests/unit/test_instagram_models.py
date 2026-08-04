from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    InstagramCollectionRunItem,
    InstagramNormalizationJob,
    InstagramReel,
)
from app.db.models.video import Video


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_video(session: Session) -> Video:
    video = Video(
        title="Canonical video",
        object_key=f"videos/{uuid4()}.mp4",
        content_type="video/mp4",
        byte_size=10,
    )
    session.add(video)
    session.commit()
    return video


def add_account(session: Session) -> InstagramAccount:
    account = InstagramAccount(status="disconnected", auto_collect_enabled=False)
    session.add(account)
    session.commit()
    return account


def add_source_ready_reel(session: Session, shortcode: str = "SAFE_CODE_001") -> InstagramReel:
    reel = InstagramReel(
        shortcode=shortcode,
        canonical_url=f"https://www.instagram.com/reel/{shortcode}/",
        pipeline_status="source_ready",
        source_object_key=f"instagram-sources/{shortcode}.mp4",
        source_sha256="a" * 64,
        source_byte_size=10,
    )
    session.add(reel)
    session.commit()
    return reel


def test_reel_unique_identity_and_ready_source_invariants(session: Session) -> None:
    reel = add_source_ready_reel(session)
    duplicate = InstagramReel(
        shortcode="SAFE_CODE_001",
        canonical_url="https://www.instagram.com/reel/OTHER/",
        pipeline_status="discovered",
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    duplicate_url = InstagramReel(
        shortcode="OTHER_CODE",
        canonical_url=reel.canonical_url,
        pipeline_status="discovered",
    )
    session.add(duplicate_url)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    missing_source = InstagramReel(
        shortcode="NO_SOURCE",
        canonical_url="https://www.instagram.com/reel/NO_SOURCE/",
        pipeline_status="source_ready",
    )
    session.add(missing_source)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    invalid_size = InstagramReel(
        shortcode="INVALID_SIZE",
        canonical_url="https://www.instagram.com/reel/INVALID_SIZE/",
        pipeline_status="discovered",
        source_byte_size=0,
    )
    session.add(invalid_size)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    for field, value in (
        ("shortcode", "  "),
        ("canonical_url", ""),
        ("source_object_key", "  "),
        ("source_sha256", "short"),
    ):
        invalid = InstagramReel(
            shortcode="VALID_CODE" if field != "shortcode" else value,
            canonical_url=(
                "https://www.instagram.com/reel/VALID_CODE/"
                if field != "canonical_url"
                else value
            ),
            pipeline_status="discovered",
            **{field: value} if field in {"source_object_key", "source_sha256"} else {},
        )
        session.add(invalid)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    ready_without_video = InstagramReel(
        shortcode="NO_VIDEO",
        canonical_url="https://www.instagram.com/reel/NO_VIDEO/",
        pipeline_status="ready",
        source_object_key="instagram-sources/no-video.mp4",
        source_sha256="b" * 64,
        source_byte_size=10,
    )
    session.add(ready_without_video)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

def test_ready_reel_references_one_existing_video_only(session: Session) -> None:
    video = add_video(session)
    first = InstagramReel(
        shortcode="READY_ONE",
        canonical_url="https://www.instagram.com/reel/READY_ONE/",
        pipeline_status="ready",
        source_object_key="instagram-sources/ready-one.mp4",
        source_sha256="c" * 64,
        source_byte_size=10,
        video_id=video.id,
    )
    session.add(first)
    session.commit()

    duplicate_video = InstagramReel(
        shortcode="READY_TWO",
        canonical_url="https://www.instagram.com/reel/READY_TWO/",
        pipeline_status="ready",
        source_object_key="instagram-sources/ready-two.mp4",
        source_sha256="d" * 64,
        source_byte_size=10,
        video_id=video.id,
    )
    session.add(duplicate_video)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    missing_video = InstagramReel(
        shortcode="MISSING_VIDEO",
        canonical_url="https://www.instagram.com/reel/MISSING_VIDEO/",
        pipeline_status="ready",
        source_object_key="instagram-sources/missing.mp4",
        source_sha256="e" * 64,
        source_byte_size=10,
        video_id=uuid4(),
    )
    session.add(missing_video)
    with pytest.raises(IntegrityError):
        session.commit()


def test_run_and_job_constraints(session: Session) -> None:
    account = add_account(session)
    reel = add_source_ready_reel(session)
    other_reel = add_source_ready_reel(session, "SAFE_CODE_002")
    run = InstagramCollectionRun(
        account_id=account.id,
        trigger="manual",
        status="queued",
        target_count=2,
    )
    session.add(run)
    session.commit()

    duplicate_active_run = InstagramCollectionRun(
        account_id=account.id,
        trigger="automatic",
        status="running",
        target_count=1,
    )
    session.add(duplicate_active_run)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    invalid_counters = InstagramCollectionRun(
        account_id=account.id,
        trigger="automatic",
        status="completed",
        target_count=1,
        source_committed_count=2,
    )
    session.add(invalid_counters)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    first_item = InstagramCollectionRunItem(
        run_id=run.id,
        reel_id=reel.id,
        position=1,
        outcome="source_committed",
        download_auth_mode="session_first",
    )
    session.add(first_item)
    session.commit()
    duplicate_position = InstagramCollectionRunItem(
        run_id=run.id,
        reel_id=other_reel.id,
        position=1,
        outcome="already_available",
        download_auth_mode=None,
    )
    session.add(duplicate_position)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    duplicate_reel = InstagramCollectionRunItem(
        run_id=run.id,
        reel_id=reel.id,
        position=2,
        outcome="source_committed",
        download_auth_mode="session_first",
    )
    session.add(duplicate_reel)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    failed_job = InstagramNormalizationJob(reel_id=other_reel.id, status="failed", attempt_count=1)
    session.add(failed_job)
    session.commit()
    retry_job = InstagramNormalizationJob(reel_id=other_reel.id, status="pending", attempt_count=0)
    session.add(retry_job)
    session.commit()
    duplicate_active_retry = InstagramNormalizationJob(
        reel_id=other_reel.id, status="running", attempt_count=0
    )
    session.add(duplicate_active_retry)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    first_job = InstagramNormalizationJob(reel_id=reel.id, status="pending", attempt_count=0)
    session.add(first_job)
    session.commit()
    duplicate_active_job = InstagramNormalizationJob(
        reel_id=reel.id, status="running", attempt_count=0
    )
    session.add(duplicate_active_job)
    with pytest.raises(IntegrityError):
        session.commit()


def test_run_item_auth_mode_truthfully_represents_download_attempts(session: Session) -> None:
    account = add_account(session)
    reels = [add_source_ready_reel(session, f"AUTH_CODE_{index}") for index in range(1, 7)]
    run = InstagramCollectionRun(
        account_id=account.id,
        trigger="manual",
        status="completed",
        target_count=6,
    )
    session.add(run)
    session.commit()

    valid_items = (
        (reels[0], 1, "source_committed", "session_first"),
        (reels[1], 2, "already_available", None),
        (reels[2], 3, "failed", None),
        (reels[3], 4, "failed", "session_first"),
    )
    for reel, position, outcome, auth_mode in valid_items:
        session.add(
            InstagramCollectionRunItem(
                run_id=run.id,
                reel_id=reel.id,
                position=position,
                outcome=outcome,
                download_auth_mode=auth_mode,
            )
        )
    session.commit()

    for reel, position, outcome, auth_mode in (
        (reels[4], 5, "source_committed", None),
        (reels[5], 6, "already_available", "session_first"),
    ):
        session.add(
            InstagramCollectionRunItem(
                run_id=run.id,
                reel_id=reel.id,
                position=position,
                outcome=outcome,
                download_auth_mode=auth_mode,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_metadata_has_no_sensitive_collections_or_columns(session: Session) -> None:
    forbidden = {
        "password",
        "two_factor",
        "cookie",
        "sessionid",
        "csrftoken",
        "storage_state",
        "authorization",
    }
    collector_tables = [
        "instagram_accounts",
        "instagram_reels",
        "instagram_collection_runs",
        "instagram_collection_run_items",
        "instagram_normalization_jobs",
    ]
    inspector = inspect(session.get_bind())
    for table in collector_tables:
        assert not (forbidden & {column["name"] for column in inspector.get_columns(table)})


def test_model_metadata_defines_postgres_partial_unique_indexes() -> None:
    indexes = {
        index.name: index
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }
    assert indexes["uq_instagram_collection_runs_active_account"].dialect_options["postgresql"][
        "where"
    ] is not None
    assert indexes["uq_instagram_normalization_jobs_active_reel"].dialect_options["postgresql"][
        "where"
    ] is not None
