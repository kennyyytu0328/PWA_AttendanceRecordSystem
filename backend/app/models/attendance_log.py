"""AttendanceLog model with WorkMode enum."""

import datetime
import enum
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class WorkMode(str, enum.Enum):
    """Where the employee is working from."""

    OFFICE = "OFFICE"
    WFH = "WFH"


class AttendanceLog(SQLModel, table=True):
    """Attendance logs table — immutable event stream of clock-in/out events."""

    __tablename__ = "attendance_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    emp_id: str = Field(foreign_key="employees.emp_id", index=True)
    timestamp: datetime.datetime = Field(
        sa_column=sa.Column(sa.DateTime, nullable=False, index=True)
    )
    latitude: float
    longitude: float
    accuracy: float
    ip_address: str
    work_mode: WorkMode = Field(
        sa_column=sa.Column(sa.Enum(WorkMode), nullable=False)
    )
    is_overridden: bool = Field(default=False)
