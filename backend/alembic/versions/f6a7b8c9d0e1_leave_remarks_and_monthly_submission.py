"""leave remarks columns, monthly_submissions table, LEAVE enum, leave_types seed

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-14 09:00:00.000000

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_LEAVE_TYPES = [
    "特休", "病假", "事假", "婚假", "喪假", "產假", "公假", "出差", "補休",
]


def upgrade() -> None:
    # 1. Add LEAVE enum value
    op.execute("ALTER TYPE attendancestatus ADD VALUE IF NOT EXISTS 'LEAVE'")

    # 2. Add leave_type + remark columns to daily_attendance_summaries
    op.add_column(
        "daily_attendance_summaries",
        sa.Column("leave_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "daily_attendance_summaries",
        sa.Column("remark", sa.String(length=500), nullable=True),
    )

    # 3. Create monthly_submissions table
    op.create_table(
        "monthly_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("emp_id", sa.String(), sa.ForeignKey("employees.emp_id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_submissions_month"),
        sa.UniqueConstraint("emp_id", "year", "month", name="uq_monthly_submission"),
    )
    op.create_index(
        "idx_monthly_submissions_lookup",
        "monthly_submissions",
        ["year", "month"],
    )

    # 4. Seed leave_types into system_config (idempotent)
    op.execute(
        sa.text(
            "INSERT INTO system_config (key, value) "
            "VALUES (:key, CAST(:value AS JSON)) "
            "ON CONFLICT (key) DO NOTHING"
        ).bindparams(
            key="leave_types",
            value=json.dumps({"types": DEFAULT_LEAVE_TYPES}),
        )
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_config WHERE key = 'leave_types'")
    op.drop_index("idx_monthly_submissions_lookup", table_name="monthly_submissions")
    op.drop_table("monthly_submissions")
    op.drop_column("daily_attendance_summaries", "remark")
    op.drop_column("daily_attendance_summaries", "leave_type")
    # LEAVE enum value cannot be removed without rebuilding the type — left as no-op.
