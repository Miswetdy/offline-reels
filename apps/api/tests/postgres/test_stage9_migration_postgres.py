"""Real PostgreSQL round-trip check for the Stage 9 viewed-history migration.

The runner starts from Alembic head, retains a representative Stage 8 reserve
snapshot, downgrades only 0009 to 0008, then upgrades back to the sole head.
It intentionally requires the disposable PostgreSQL environment so SQLite
cannot mask PostgreSQL DDL or transaction behaviour.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.settings import get_settings
from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionSettings,
    ManagementReserveDevice,
)
from app.db.session import create_session_factory
from app.instagram.contracts import AccountStatus

API_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sessions() -> sessionmaker[Session]:
    if os.environ.get("STAGE9_REAL_POSTGRES") != "1":
        pytest.fail("set STAGE9_REAL_POSTGRES=1; this test requires disposable PostgreSQL")
    return create_session_factory(get_settings())


def _alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def _stage8_snapshot(sessions: sessionmaker[Session]) -> tuple[object, ...]:
    with sessions() as db:
        reserve = db.scalar(select(ManagementReserveDevice))
        settings = db.scalar(select(InstagramCollectionSettings))
        assert reserve is not None and settings is not None
        return (
            reserve.id,
            reserve.account_id,
            reserve.device_uuid,
            reserve.auto_refill_enabled,
            reserve.local_completed_count,
            reserve.desired_count,
            reserve.low_watermark,
            reserve.quota_threshold,
            reserve.reported_at,
            settings.account_id,
            settings.enabled,
            settings.target_reserve,
        )


def test_upgrade_downgrade_0008_upgrade_preserves_stage8_reserve_data(
    sessions: sessionmaker[Session],
) -> None:
    """0009 may be reversible without changing historical Stage 8 records."""
    account_id = uuid4()
    reported_at = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    with sessions.begin() as db:
        db.add(InstagramAccount(id=account_id, status=AccountStatus.CONNECTED.value))
        db.add(InstagramCollectionSettings(account_id=account_id, enabled=True, target_reserve=7))
        db.add(
            ManagementReserveDevice(
                account_id=account_id,
                device_uuid=uuid4(),
                auto_refill_enabled=True,
                local_completed_count=6,
                desired_count=12,
                low_watermark=4,
                quota_threshold=75,
                reported_at=reported_at,
            )
        )

    before = _stage8_snapshot(sessions)
    config = _alembic_config()
    assert ScriptDirectory.from_config(config).get_heads() == ["0009_instagram_reel_views"]

    command.downgrade(config, "0008_reserve_device_reports")
    with sessions() as db:
        assert "instagram_reel_views" not in inspect(db.get_bind()).get_table_names()
    assert _stage8_snapshot(sessions) == before

    command.upgrade(config, "head")
    with sessions() as db:
        assert "instagram_reel_views" in inspect(db.get_bind()).get_table_names()
    assert _stage8_snapshot(sessions) == before
