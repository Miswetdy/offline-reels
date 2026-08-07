"""Run the network-free Collector engine against deterministic fixtures."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.instagram import InstagramAccount, InstagramReel
from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.fixtures import (
    FixtureDownloader,
    FixtureFeed,
    FixtureRollbackFailingPersistence,
    FixtureValidator,
    LocalFixtureSourceStorage,
)
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.collector.service import CollectorEngine
from app.instagram.contracts import CollectionTrigger, ReelPipelineStatus

SCENARIOS = {
    "happy",
    "already-available",
    "download-failure",
    "validation-failure",
    "storage-failure",
    "db-commit-failure",
    "db-commit-compensation-failure",
    "repeated-shortcode",
    "transition-timeout",
}
FIXTURES = tuple(
    ReelCandidate(f"FIXTURE_{number:03d}", f"https://www.instagram.com/reel/FIXTURE_{number:03d}/")
    for number in range(1, 6)
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Network-free Instagram Collector fixture mode.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="happy")
    parser.add_argument("--target", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    owned_workspace = args.workspace is None
    workspace = (
        args.workspace
        or Path(tempfile.mkdtemp(prefix="offline-reels-collector-fixture-"))
    ).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        summary = run_fixture(workspace, args.scenario, args.target)
        print(json.dumps(_safe_summary(summary), sort_keys=True))
        return 0 if summary.status == "completed" else 1
    finally:
        if owned_workspace:
            shutil.rmtree(workspace, ignore_errors=True)


def run_fixture(workspace: Path, scenario: str, target: int):
    engine = create_engine(f"sqlite+pysqlite:///{workspace / 'fixture.sqlite3'}")
    try:
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with sessions.begin() as session:
            account = session.query(InstagramAccount).first()
            if account is None:
                account = InstagramAccount(
                    id=uuid4(),
                    status="connected",
                    auto_collect_enabled=False,
                )
                session.add(account)
        with sessions() as session:
            account_id = session.query(InstagramAccount.id).first()[0]
        if scenario == "already-available":
            with sessions.begin() as session:
                existing = session.query(InstagramReel).filter_by(
                    shortcode=FIXTURES[0].shortcode
                ).first()
                if existing is None:
                    session.add(
                        InstagramReel(
                            shortcode=FIXTURES[0].shortcode,
                            canonical_url=FIXTURES[0].canonical_url,
                            pipeline_status=ReelPipelineStatus.SOURCE_READY.value,
                            source_object_key="instagram-sources/FIXTURE_001.mp4",
                            source_sha256="a" * 64,
                            source_byte_size=1,
                        )
                    )
        candidates = list(FIXTURES)
        if scenario == "repeated-shortcode":
            candidates = [FIXTURES[0], FIXTURES[0]]
        feed = FixtureFeed(candidates, transition_timeout=scenario == "transition-timeout")
        if scenario in {"db-commit-failure", "db-commit-compensation-failure"}:
            persistence = FixtureRollbackFailingPersistence(sessions)
        else:
            persistence = CollectorPersistence(sessions)
        return CollectorEngine(
            persistence,
            feed,
            FixtureDownloader(fail=scenario == "download-failure"),
            FixtureValidator(fail=scenario == "validation-failure"),
            LocalFixtureSourceStorage(
                workspace / "sources",
                fail_publish=scenario == "storage-failure",
                fail_delete=scenario == "db-commit-compensation-failure",
            ),
        ).collect(account_id, CollectionTrigger.MANUAL, target)
    finally:
        engine.dispose()


def _safe_summary(summary) -> dict[str, object]:
    return {
        "phase": "fixture-collector",
        "status": summary.status,
        "target_count": summary.target_count,
        "source_committed_count": summary.source_committed_count,
        "already_available_count": summary.already_available_count,
        "failed_count": summary.failed_count,
        "confirmed_advances": summary.confirmed_advances,
        "stop_reason_code": summary.stop_reason_code,
    }


if __name__ == "__main__":
    raise SystemExit(main())
