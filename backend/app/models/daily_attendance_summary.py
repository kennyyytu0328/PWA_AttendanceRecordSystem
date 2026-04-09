"""DailyAttendanceSummary model with AttendanceStatus enum."""

import datetime
import enum
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class AttendanceStatus(str, enum.Enum):
    """Daily attendance status classification."""

    NORMAL = "NORMAL"
    LATE = "LATE"
    EARLY_LEAVE = "EARLY_LEAVE"
    LATE_AND_EARLY_LEAVE = "LATE_AND_EARLY_LEAVE"
    ABNORMAL = "ABNORMAL"


class DailyAttendanceSummary(SQLModel, table=True):
    """Daily attendance summaries — one row per employee per date."""

    __tablename__ = "daily_attendance_summaries"
    __table_args__ = (
        sa.UniqueConstraint("emp_id", "date", name="uq_summary_emp_date"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    emp_id: str = Field(foreign_key="employees.emp_id")
    date: datetime.date
    first_clock_in: Optional[datetime.datetime] = Field(default=None)
    last_clock_out: Optional[datetime.datetime] = Field(default=None)
    status: AttendanceStatus = Field(
        sa_column=sa.Column(sa.Enum(AttendanceStatus), nullable=False)
    )
