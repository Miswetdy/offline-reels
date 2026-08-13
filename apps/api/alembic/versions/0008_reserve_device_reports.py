"""Add safe PWA local-reserve device reports.

Revision ID: 0008_reserve_device_reports
Revises: 0007_management_control_plane
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_reserve_device_reports"
down_revision: str | Sequence[str] | None = "0007_management_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "management_reserve_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_uuid", sa.Uuid(), nullable=False),
        sa.Column("auto_refill_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("local_completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("desired_count", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("low_watermark", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("quota_threshold", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "local_completed_count >= 0", name="ck_reserve_device_completed_nonnegative"
        ),
        sa.CheckConstraint(
            "desired_count >= 1 AND desired_count <= 100", name="ck_reserve_device_desired_range"
        ),
        sa.CheckConstraint(
            "low_watermark >= 0 AND low_watermark < desired_count",
            name="ck_reserve_device_watermark_range",
        ),
        sa.CheckConstraint(
            "quota_threshold >= 50 AND quota_threshold <= 95",
            name="ck_reserve_device_quota_range",
        ),
    )
    op.create_index(
        "uq_management_reserve_devices_account_device",
        "management_reserve_devices",
        ["account_id", "device_uuid"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_management_reserve_devices_account_device", table_name="management_reserve_devices"
    )
    op.drop_table("management_reserve_devices")
