"""add LATE_AND_EARLY_LEAVE status enum value

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-08 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add LATE_AND_EARLY_LEAVE to attendancestatus enum."""
    op.execute("ALTER TYPE attendancestatus ADD VALUE IF NOT EXISTS 'LATE_AND_EARLY_LEAVE'")


def downgrade() -> None:
    """PostgreSQL does not support removing enum values easily."""
    pass
