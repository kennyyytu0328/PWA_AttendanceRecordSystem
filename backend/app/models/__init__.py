"""Database models — import all models so SQLModel.metadata registers them."""

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.attendance_reason import AttendanceReason
from app.models.authenticator import Authenticator
from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary
from app.models.employee import Employee, Role
from app.models.system_config import SystemConfig

__all__ = [
    "AttendanceLog",
    "AttendanceReason",
    "AttendanceStatus",
    "Authenticator",
    "DailyAttendanceSummary",
    "Employee",
    "Role",
    "SystemConfig",
    "WorkMode",
]
