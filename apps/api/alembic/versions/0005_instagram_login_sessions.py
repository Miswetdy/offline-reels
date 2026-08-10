"""Add short-lived, token-hashed remote Instagram login sessions.

Revision ID: 0005_instagram_login_sessions
Revises: 0004_instagram_collector_foundation
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_instagram_login_sessions"
down_revision: str | Sequence[str] | None = "0004_instagram_collector_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instagram_login_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("prior_account_status", sa.String(length=32), nullable=False),
        sa.Column("launch_token_hash", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'completed', 'expired', 'cancelled')",
            name="ck_instagram_login_sessions_status",
        ),
        sa.CheckConstraint(
            "length(launch_token_hash) = 64",
            name="ck_login_session_token_hash_length",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("launch_token_hash"),
    )
    op.create_index(
        "uq_instagram_login_sessions_active_account",
        "instagram_login_sessions",
        ["account_id"], unique=True,
        postgresql_where=sa.text("status IN ('pending', 'active')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_instagram_login_sessions_active_account",
        table_name="instagram_login_sessions",
    )
    op.drop_table("instagram_login_sessions")
