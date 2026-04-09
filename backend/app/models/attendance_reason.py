"""AttendanceReason model — stores employee-submitted reasons for tardiness."""

import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class AttendanceReason(SQLModel, table=True):
    """Employee-submitted reason for LATE or EARLY_LEAVE status."""

    __tablename__ = "attendance_reasons"
    __table_args__ = (
        sa.UniqueConstraint("summary_id", name="uq_reason_summary"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    summary_id: int = Field(foreign_key="daily_attendance_summaries.id")
    emp_id: str = Field(foreign_key="employees.emp_id")
    reason: str = Field(max_length=500)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now
    )
