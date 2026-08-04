from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.models.instagram import (
    InstagramCollectionRun,
    InstagramCollectionRunItem,
    InstagramReel,
)

API_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_has_one_collector_head_after_video_normalization() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["0004_instagram_collector_foundation"]
    revision = script.get_revision("0004_instagram_collector_foundation")
    assert revision is not None
    assert revision.down_revision == "0003_video_normalization"


def test_collector_model_ddl_carries_source_and_run_integrity_rules() -> None:
    reel_sql = str(CreateTable(InstagramReel.__table__).compile(dialect=postgresql.dialect()))
    item_sql = str(
        CreateTable(InstagramCollectionRunItem.__table__).compile(dialect=postgresql.dialect())
    )
    run_sql = str(
        CreateTable(InstagramCollectionRun.__table__).compile(dialect=postgresql.dialect())
    )
    assert "ck_reels_source_required" in reel_sql
    assert "ck_reels_ready_requires_video" in reel_sql
    assert "ck_reels_shortcode_nonempty" in reel_sql
    assert "ck_reels_source_sha256_length" in reel_sql
    assert "ck_collection_run_items_auth_mode_outcome" in item_sql
    assert "download_auth_mode VARCHAR(32)" in item_sql
    assert "ck_collection_runs_counters_within_target" in run_sql
    assert "ck_collection_runs_target_positive" in run_sql


def test_migration_defines_only_safe_schema_columns() -> None:
    migration = (
        API_ROOT / "alembic" / "versions" / "0004_instagram_collector_foundation.py"
    ).read_text(encoding="utf-8").lower()
    forbidden_columns = (
        "password",
        "cookie",
        "sessionid",
        "csrftoken",
        "storage_state",
        "authorization",
    )
    for forbidden in forbidden_columns:
        assert f'column("{forbidden}"' not in migration
    assert "postgresql_where" in migration
    assert "source_ready" in migration
    assert "ck_collection_run_items_auth_mode_outcome" in migration
    assert 'sa.column("download_auth_mode", sa.string(length=32), nullable=true)' in migration
    assert '"alembic_version"' in migration
    assert "sa.string(length=64)" in migration
