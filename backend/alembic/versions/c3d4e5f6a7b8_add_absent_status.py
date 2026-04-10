"""add ABSENT status enum value

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-10 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ABSENT to attendancestatus enum."""
    op.execute("ALTER TYPE attendancestatus ADD VALUE IF NOT EXISTS 'ABSENT'")


def downgrade() -> None:
    """PostgreSQL does not support removing enum values easily."""
    pass
