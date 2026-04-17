"""add terminated_at to employees

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-17 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable terminated_at timestamp column to employees."""
    op.add_column(
        "employees",
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_employees_terminated_at",
        "employees",
        ["terminated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_employees_terminated_at", table_name="employees")
    op.drop_column("employees", "terminated_at")
