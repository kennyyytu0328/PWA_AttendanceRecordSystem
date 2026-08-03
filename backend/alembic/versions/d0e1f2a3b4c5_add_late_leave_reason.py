"""add late_leave_reason to daily_attendance_summaries

Stores why an employee left work after their shift end
("ASSIGNED_OVERTIME" | "PERSONAL"). Nullable — most days have no late leave.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_attendance_summaries",
        sa.Column("late_leave_reason", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_attendance_summaries", "late_leave_reason")
