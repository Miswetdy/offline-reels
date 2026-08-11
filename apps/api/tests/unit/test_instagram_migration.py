from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.models.instagram import (
    InstagramCollectionRun,
    InstagramCollectionRunItem,
    InstagramLoginSession,
    InstagramReel,
    ManagementDeviceSession,
    ManagementPairingChallenge,
)

API_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_has_one_collector_head_after_video_normalization() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["0007_management_control_plane"]
    revision = script.get_revision("0007_management_control_plane")
    assert revision is not None
    assert revision.down_revision == "0006_instagram_normalizer_runtime"


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


def test_login_session_ddl_and_migration_never_store_browser_secrets() -> None:
    sql = str(CreateTable(InstagramLoginSession.__table__).compile(dialect=postgresql.dialect()))
    migration = (
        (API_ROOT / "alembic" / "versions" / "0005_instagram_login_sessions.py")
        .read_text(encoding="utf-8")
        .lower()
    )
    active_index = next(
        index
        for index in InstagramLoginSession.__table__.indexes
        if index.name == "uq_instagram_login_sessions_active_account"
    )
    index_sql = str(CreateIndex(active_index).compile(dialect=postgresql.dialect()))
    assert "uq_instagram_login_sessions_active_account" in index_sql
    assert "launch_token_hash" in sql
    for forbidden in ("password", "cookie", "sessionid", "csrftoken", "storage_state", "captcha"):
        assert f'column("{forbidden}"' not in migration


def test_migration_defines_only_safe_schema_columns() -> None:
    migration = (
        (API_ROOT / "alembic" / "versions" / "0004_instagram_collector_foundation.py")
        .read_text(encoding="utf-8")
        .lower()
    )
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


def test_management_schema_has_hashes_but_no_plaintext_secrets() -> None:
    pair_sql = str(
        CreateTable(ManagementPairingChallenge.__table__).compile(dialect=postgresql.dialect())
    )
    session_sql = str(
        CreateTable(ManagementDeviceSession.__table__).compile(dialect=postgresql.dialect())
    )
    migration = (
        (API_ROOT / "alembic" / "versions" / "0007_management_control_plane.py")
        .read_text(encoding="utf-8")
        .lower()
    )
    assert "secret_hash" in pair_sql
    assert "session_token_hash" in session_sql and "csrf_token_hash" in session_sql
    for forbidden in ('"secret",', '"token",', '"csrf",', "request_body"):
        assert forbidden not in migration
