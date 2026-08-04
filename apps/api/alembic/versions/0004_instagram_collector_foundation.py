"""Add durable Instagram Collector domain tables.

Revision ID: 0004_instagram_collector_foundation
Revises: 0003_video_normalization
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_instagram_collector_foundation"
down_revision: str | Sequence[str] | None = "0003_video_normalization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic creates this control-table column as VARCHAR(32), while this
    # accepted revision identifier is longer. Widen it before Alembic records
    # the target revision after this migration completes.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.create_table(
        "instagram_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("auto_collect_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reauth_required_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('disconnected', 'connecting', 'connected', 'reauth_required', "
            "'temporarily_limited')",
            name="ck_instagram_accounts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "instagram_reels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shortcode", sa.String(length=64), nullable=False),
        sa.Column("canonical_url", sa.String(length=512), nullable=False),
        sa.Column("pipeline_status", sa.String(length=32), nullable=False),
        sa.Column("source_object_key", sa.String(length=512), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_byte_size", sa.BigInteger(), nullable=True),
        sa.Column("video_id", sa.Uuid(), nullable=True),
        sa.Column("failure_reason_code", sa.String(length=64), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pipeline_status IN ('discovered', 'downloading', 'source_ready', 'normalizing', "
            "'ready', 'failed')",
            name="ck_instagram_reels_status",
        ),
        sa.CheckConstraint("length(trim(shortcode)) > 0", name="ck_reels_shortcode_nonempty"),
        sa.CheckConstraint(
            "length(trim(canonical_url)) > 0", name="ck_reels_canonical_url_nonempty"
        ),
        sa.CheckConstraint(
            "source_object_key IS NULL OR length(trim(source_object_key)) > 0",
            name="ck_reels_source_object_key_nonempty",
        ),
        sa.CheckConstraint(
            "source_sha256 IS NULL OR length(source_sha256) = 64",
            name="ck_reels_source_sha256_length",
        ),
        sa.CheckConstraint(
            "source_byte_size IS NULL OR source_byte_size > 0", name="ck_reels_size_positive"
        ),
        sa.CheckConstraint(
            "pipeline_status NOT IN ('source_ready', 'normalizing', 'ready') "
            "OR (source_object_key IS NOT NULL AND source_sha256 IS NOT NULL "
            "AND source_byte_size IS NOT NULL AND source_byte_size > 0)",
            name="ck_reels_source_required",
        ),
        sa.CheckConstraint(
            "pipeline_status <> 'ready' OR video_id IS NOT NULL",
            name="ck_reels_ready_requires_video",
        ),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_url"),
        sa.UniqueConstraint("shortcode"),
        sa.UniqueConstraint("source_object_key"),
        sa.UniqueConstraint("video_id"),
    )
    op.create_table(
        "instagram_collection_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("source_committed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("already_available_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stop_reason_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("trigger IN ('manual', 'automatic')", name="ck_collection_runs_trigger"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'cancelled', 'failed')",
            name="ck_collection_runs_status",
        ),
        sa.CheckConstraint("target_count > 0", name="ck_collection_runs_target_positive"),
        sa.CheckConstraint(
            "source_committed_count >= 0 AND already_available_count >= 0 AND failed_count >= 0",
            name="ck_collection_runs_counters_nonnegative",
        ),
        sa.CheckConstraint(
            "source_committed_count + already_available_count + failed_count <= target_count",
            name="ck_collection_runs_counters_within_target",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_instagram_collection_runs_active_account",
        "instagram_collection_runs",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "instagram_collection_run_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("reel_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("download_auth_mode", sa.String(length=32), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('source_committed', 'already_available', 'failed')",
            name="ck_collection_run_items_outcome",
        ),
        sa.CheckConstraint(
            "download_auth_mode IN ('session_first')", name="ck_collection_run_items_auth_mode"
        ),
        sa.CheckConstraint(
            "(outcome = 'source_committed' AND download_auth_mode IS NOT NULL) "
            "OR (outcome = 'already_available' AND download_auth_mode IS NULL) "
            "OR (outcome = 'failed' AND (download_auth_mode IS NULL "
            "OR download_auth_mode = 'session_first'))",
            name="ck_collection_run_items_auth_mode_outcome",
        ),
        sa.CheckConstraint("position > 0", name="ck_collection_run_items_position_positive"),
        sa.ForeignKeyConstraint(["reel_id"], ["instagram_reels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["instagram_collection_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_instagram_collection_run_items_run_position",
        "instagram_collection_run_items",
        ["run_id", "position"],
        unique=True,
    )
    op.create_index(
        "uq_instagram_collection_run_items_run_reel",
        "instagram_collection_run_items",
        ["run_id", "reel_id"],
        unique=True,
    )
    op.create_table(
        "instagram_normalization_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reel_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_normalization_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_normalization_jobs_attempt_nonnegative"),
        sa.ForeignKeyConstraint(["reel_id"], ["instagram_reels.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_instagram_normalization_jobs_active_reel",
        "instagram_normalization_jobs",
        ["reel_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_instagram_normalization_jobs_active_reel",
        table_name="instagram_normalization_jobs",
    )
    op.drop_table("instagram_normalization_jobs")
    op.drop_index(
        "uq_instagram_collection_run_items_run_reel",
        table_name="instagram_collection_run_items",
    )
    op.drop_index(
        "uq_instagram_collection_run_items_run_position",
        table_name="instagram_collection_run_items",
    )
    op.drop_table("instagram_collection_run_items")
    op.drop_index(
        "uq_instagram_collection_runs_active_account",
        table_name="instagram_collection_runs",
    )
    op.drop_table("instagram_collection_runs")
    op.drop_table("instagram_reels")
    op.drop_table("instagram_accounts")
    # Keep Alembic's control column widened. Alembic writes the target revision
    # only after this downgrade body runs, while the current 0004 identifier
    # exceeds VARCHAR(32); narrowing here would make the downgrade impossible.
