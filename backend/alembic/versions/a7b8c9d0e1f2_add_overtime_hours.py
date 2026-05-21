"""add overtime_hours to daily_attendance_summaries

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-21 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_attendance_summaries",
        sa.Column("overtime_hours", sa.Numeric(3, 1), nullable=True),
    )
    op.create_check_constraint(
        "ck_summary_overtime_hours_step",
        "daily_attendance_summaries",
        "overtime_hours IS NULL OR ("
        "overtime_hours >= 1.0 AND (overtime_hours * 2) = FLOOR(overtime_hours * 2)"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_summary_overtime_hours_step",
        "daily_attendance_summaries",
        type_="check",
    )
    op.drop_column("daily_attendance_summaries", "overtime_hours")
