"""Add normalization worker lease, publication and cleanup state.

Revision ID: 0006_instagram_normalizer_runtime
Revises: 0005_instagram_login_sessions
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_instagram_normalizer_runtime"
down_revision: str | Sequence[str] | None = "0005_instagram_login_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "instagram_reels",
        sa.Column(
            "source_cleanup_pending", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "instagram_normalization_jobs", sa.Column("claimed_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "instagram_normalization_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column("instagram_normalization_jobs", sa.Column("worker_id", sa.String(length=64)))
    op.add_column(
        "instagram_normalization_jobs", sa.Column("staging_prefix", sa.String(length=512))
    )
    op.create_index(
        "ix_instagram_normalization_jobs_lease_expires_at",
        "instagram_normalization_jobs",
        ["lease_expires_at"],
    )
    op.add_column("videos", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_videos_content_sha256", "videos", ["content_sha256"])


def downgrade() -> None:
    op.drop_constraint("uq_videos_content_sha256", "videos", type_="unique")
    op.drop_column("videos", "content_sha256")
    op.drop_index(
        "ix_instagram_normalization_jobs_lease_expires_at", "instagram_normalization_jobs"
    )
    op.drop_column("instagram_normalization_jobs", "staging_prefix")
    op.drop_column("instagram_normalization_jobs", "worker_id")
    op.drop_column("instagram_normalization_jobs", "lease_expires_at")
    op.drop_column("instagram_normalization_jobs", "claimed_at")
    op.drop_column("instagram_reels", "source_cleanup_pending")
