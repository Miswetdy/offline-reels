"""Store account-scoped, first-confirmed Reel views.

Revision ID: 0009_instagram_reel_views
Revises: 0008_reserve_device_reports
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_instagram_reel_views"
down_revision: str | Sequence[str] | None = "0008_reserve_device_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instagram_reel_views",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reel_id",
            sa.Uuid(),
            sa.ForeignKey("instagram_reels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("device_uuid", sa.Uuid(), nullable=True),
        sa.Column(
            "viewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_instagram_reel_views_account_reel",
        "instagram_reel_views",
        ["account_id", "reel_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_instagram_reel_views_account_reel", table_name="instagram_reel_views")
    op.drop_table("instagram_reel_views")
