"""MonthlySubmission model — per-employee per-month confirmation flag."""

import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class MonthlySubmission(SQLModel, table=True):
    """One row per (employee, year, month) marking the month as 'submitted'."""

    __tablename__ = "monthly_submissions"
    __table_args__ = (
        sa.UniqueConstraint("emp_id", "year", "month", name="uq_monthly_submission"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_submissions_month"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    emp_id: str = Field(foreign_key="employees.emp_id")
    year: int
    month: int
    submitted_at: datetime.datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
