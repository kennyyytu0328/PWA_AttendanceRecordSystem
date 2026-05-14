"""Tests for LEAVE enum value and remark columns."""
import datetime

from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary
from app.services.reporting_service import calculate_status


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


SHIFT_START = datetime.time(9, 0)
SHIFT_END = datetime.time(18, 0)


def test_leave_type_set_returns_LEAVE_even_when_late():
    late_clock_in = datetime.datetime(2026, 5, 14, 10, 30)
    status = calculate_status(
        SHIFT_START, SHIFT_END,
        first_clock_in=late_clock_in,
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        leave_type="特休",
    )
    assert status == AttendanceStatus.LEAVE


def test_leave_type_set_with_no_punches_returns_LEAVE_not_None():
    status = calculate_status(
        SHIFT_START, SHIFT_END,
        first_clock_in=None,
        last_clock_out=None,
        leave_type="病假",
    )
    assert status == AttendanceStatus.LEAVE


def test_leave_type_none_preserves_existing_logic():
    on_time = datetime.datetime(2026, 5, 14, 9, 0)
    status = calculate_status(
        SHIFT_START, SHIFT_END,
        first_clock_in=on_time,
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        leave_type=None,
    )
    assert status == AttendanceStatus.NORMAL


def test_empty_leave_type_string_treated_as_none():
    # Defensive: empty string is not a valid leave selection
    late = datetime.datetime(2026, 5, 14, 10, 30)
    status = calculate_status(
        SHIFT_START, SHIFT_END,
        first_clock_in=late,
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        leave_type="",
    )
    assert status == AttendanceStatus.LATE
