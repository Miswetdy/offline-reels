"""Add nullable normalization metadata to videos.

Revision ID: 0003_video_normalization
Revises: 0002_create_videos
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_video_normalization"
down_revision: str | Sequence[str] | None = "0002_create_videos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("normalization_strategy", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "videos",
        sa.Column("original_video_codec", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "videos",
        sa.Column("normalized_video_codec", sa.String(length=64), nullable=True),
    )
    op.add_column("videos", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("videos", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("videos", sa.Column("duration_ms", sa.BigInteger(), nullable=True))
    op.add_column("videos", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("videos", sa.Column("has_audio", sa.Boolean(), nullable=True))
    op.add_column("videos", sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "normalized_at")
    op.drop_column("videos", "has_audio")
    op.drop_column("videos", "file_size_bytes")
    op.drop_column("videos", "duration_ms")
    op.drop_column("videos", "height")
    op.drop_column("videos", "width")
    op.drop_column("videos", "normalized_video_codec")
    op.drop_column("videos", "original_video_codec")
    op.drop_column("videos", "normalization_strategy")
