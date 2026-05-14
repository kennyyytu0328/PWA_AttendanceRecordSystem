"""Tests for LEAVE enum value and remark columns."""
from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary


def test_leave_enum_value_exists():
    assert AttendanceStatus.LEAVE.value == "LEAVE"


def test_summary_model_has_leave_type_and_remark():
    summary = DailyAttendanceSummary(
        emp_id="E001",
        date="2026-05-14",
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休",
        remark="上午",
    )
    assert summary.leave_type == "特休"
    assert summary.remark == "上午"
