"""Bootstrap the Editorial OS database migration chain.

Revision ID: 20260928_0001
Revises:
Create Date: 2026-09-28
"""

from collections.abc import Sequence

revision: str = "20260928_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No domain tables yet; Issue #3 owns the first editorial schema."""


def downgrade() -> None:
    """Return to the empty pre-runtime schema."""
