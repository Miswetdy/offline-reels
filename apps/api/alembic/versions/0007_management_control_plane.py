"""Add protected management control-plane state.

Revision ID: 0007_management_control_plane
Revises: 0006_instagram_normalizer_runtime
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_management_control_plane"
down_revision: str | Sequence[str] | None = "0006_instagram_normalizer_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("instagram_login_sessions", sa.Column("claimed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "instagram_collection_runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True))
    )
    op.create_table(
        "management_pairing_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("instagram_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("secret_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "length(secret_hash) = 64", name="ck_management_pairing_secret_hash_length"
        ),
    )
    op.create_table(
        "management_device_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("instagram_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("session_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "length(session_token_hash) = 64", name="ck_management_session_hash_length"
        ),
        sa.CheckConstraint("length(csrf_token_hash) = 64", name="ck_management_csrf_hash_length"),
    )
    op.create_index(
        "ix_management_device_sessions_expires_at", "management_device_sessions", ["expires_at"]
    )
    op.create_table(
        "management_idempotency_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("management_device_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_json", sa.String(2048), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "length(key_hash) = 64", name="ck_management_idempotency_key_hash_length"
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64", name="ck_management_idempotency_fingerprint_length"
        ),
    )
    op.create_index(
        "uq_management_idempotency_scope",
        "management_idempotency_records",
        ["session_id", "operation", "key_hash"],
        unique=True,
    )
    op.create_index(
        "ix_management_idempotency_expires_at", "management_idempotency_records", ["expires_at"]
    )
    op.create_table(
        "instagram_collection_settings",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("target_reserve", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "target_reserve >= 1 AND target_reserve <= 10",
            name="ck_collection_settings_target_range",
        ),
    )
    op.create_table(
        "management_rate_limits",
        sa.Column("scope_hash", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("management_rate_limits")
    op.drop_table("instagram_collection_settings")
    op.drop_index(
        "ix_management_idempotency_expires_at", table_name="management_idempotency_records"
    )
    op.drop_index("uq_management_idempotency_scope", table_name="management_idempotency_records")
    op.drop_table("management_idempotency_records")
    op.drop_index(
        "ix_management_device_sessions_expires_at", table_name="management_device_sessions"
    )
    op.drop_table("management_device_sessions")
    op.drop_table("management_pairing_challenges")
    op.drop_column("instagram_collection_runs", "cancel_requested_at")
    op.drop_column("instagram_login_sessions", "claimed_at")
