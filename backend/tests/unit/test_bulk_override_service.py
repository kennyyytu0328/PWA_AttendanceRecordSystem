"""Tests for bulk punch override service logic."""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role

_SERVICE = "app.services.attendance_service"
_ATTENDANCE_REPO = "app.repositories.attendance_repository"
_SUMMARY_REPO = "app.repositories.summary_repository"
_REPORTING = "app.services.reporting_service"
_EMPLOYEE_REPO = "app.repositories.employee_repository"


def _make_employee(emp_id: str = "EMP100", role: Role = Role.EMPLOYEE) -> Employee:
    return Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=role,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )


@pytest.mark.asyncio
async def test_bulk_override_creates_new_logs(db_session: AsyncSession):
    """Bulk override creates new attendance log entries."""
    from app.services.attendance_service import bulk_override_punches

    employee = _make_employee()
    db_session.add(employee)
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(8, 55), "last_clock_out": datetime.time(18, 5)},
    ]

    with patch(f"{_REPORTING}.generate_daily_summary", new_callable=AsyncMock, return_value=None):
        result = await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )

    assert result["updated_count"] == 1
    assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_bulk_override_marks_old_logs_overridden(db_session: AsyncSession):
    """Existing logs should be marked as is_overridden=True."""
    from app.services.attendance_service import bulk_override_punches

    employee = _make_employee()
    db_session.add(employee)

    old_log = AttendanceLog(
        emp_id="EMP100",
        timestamp=datetime.datetime(2026, 4, 1, 9, 0, 0),
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="127.0.0.1",
        work_mode=WorkMode.OFFICE,
        is_overridden=False,
    )
    db_session.add(old_log)
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(8, 50), "last_clock_out": datetime.time(18, 10)},
    ]

    with patch(f"{_REPORTING}.generate_daily_summary", new_callable=AsyncMock, return_value=None):
        await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )

    await db_session.refresh(old_log)
    assert old_log.is_overridden is True


@pytest.mark.asyncio
async def test_bulk_override_recalculates_summaries(db_session: AsyncSession):
    """Summaries should be regenerated for overridden dates."""
    from app.services.attendance_service import bulk_override_punches

    employee = _make_employee()
    db_session.add(employee)
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(8, 55), "last_clock_out": datetime.time(18, 5)},
        {"date": datetime.date(2026, 4, 2), "first_clock_in": datetime.time(9, 0), "last_clock_out": datetime.time(18, 0)},
    ]

    mock_generate = AsyncMock(return_value=None)
    with patch(f"{_REPORTING}.generate_daily_summary", mock_generate):
        await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )

    assert mock_generate.call_count == 2


@pytest.mark.asyncio
async def test_bulk_override_employee_cannot_override_others(db_session: AsyncSession):
    """EMPLOYEE role cannot override another employee's punches."""
    from app.services.attendance_service import bulk_override_punches

    db_session.add(_make_employee("EMP100", Role.EMPLOYEE))
    db_session.add(_make_employee("EMP200", Role.EMPLOYEE))
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(9, 0), "last_clock_out": datetime.time(18, 0)},
    ]

    with pytest.raises(PermissionError, match="cannot override"):
        await bulk_override_punches(
            db_session,
            emp_id="EMP200",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )


@pytest.mark.asyncio
async def test_bulk_override_hr_can_override_others(db_session: AsyncSession):
    """HR role can override any employee's punches."""
    from app.services.attendance_service import bulk_override_punches

    db_session.add(_make_employee("EMP100", Role.EMPLOYEE))
    db_session.add(_make_employee("HR001", Role.HR))
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(9, 0), "last_clock_out": datetime.time(18, 0)},
    ]

    with patch(f"{_REPORTING}.generate_daily_summary", new_callable=AsyncMock, return_value=None):
        result = await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="HR001",
            requesting_user_role=Role.HR,
            entries=entries,
        )

    assert result["updated_count"] == 1


@pytest.mark.asyncio
async def test_bulk_override_employee_not_found(db_session: AsyncSession):
    """Raises ValueError if target employee not found."""
    from app.services.attendance_service import bulk_override_punches

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(9, 0), "last_clock_out": datetime.time(18, 0)},
    ]

    with pytest.raises(ValueError, match="not found"):
        await bulk_override_punches(
            db_session,
            emp_id="NONEXISTENT",
            requesting_user_id="NONEXISTENT",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )


@pytest.mark.asyncio
async def test_bulk_override_skip_entry_with_no_times(db_session: AsyncSession):
    """Entries with both clock_in and clock_out as None should be skipped."""
    from app.services.attendance_service import bulk_override_punches

    db_session.add(_make_employee())
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": None, "last_clock_out": None},
    ]

    with patch(f"{_REPORTING}.generate_daily_summary", new_callable=AsyncMock, return_value=None):
        result = await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )

    assert result["updated_count"] == 0
