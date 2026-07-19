"""Initial empty schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-19
"""

from collections.abc import Sequence

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create no application tables during the bootstrap stage."""
    pass


def downgrade() -> None:
    """Revert the empty bootstrap migration."""
    pass
