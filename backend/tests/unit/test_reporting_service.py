"""Unit tests for Reporting Service — Phase 3F (TDD).

Tests cover:
- Status calculation (NORMAL, LATE, EARLY_LEAVE, ABNORMAL)
- First-In / Last-Out logic
- Grace period boundary
- Daily summary generation (single + batch)
- CSV and JSON export with date-range and department filters
"""

import csv
import datetime
import io
import json

from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_employee(
    session: AsyncSession,
    emp_id: str = "EMP001",
    name: str = "Test User",
    department: str = "Engineering",
    shift_start: datetime.time = datetime.time(9, 0),
    shift_end: datetime.time = datetime.time(18, 0),
) -> Employee:
    """Insert an employee so FK constraints are satisfied."""
    emp = Employee(
        emp_id=emp_id,
        name=name,
        department=department,
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=shift_start,
        shift_end_time=shift_end,
    )
    session.add(emp)
    await session.commit()
    return emp


async def _create_attendance_log(
    session: AsyncSession,
    emp_id: str,
    timestamp: datetime.datetime,
) -> AttendanceLog:
    """Insert an attendance log entry."""
    log = AttendanceLog(
        emp_id=emp_id,
        timestamp=timestamp,
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="192.168.1.1",
        work_mode=WorkMode.OFFICE,
        is_overridden=False,
    )
    session.add(log)
    await session.commit()
    return log


# ---------------------------------------------------------------------------
# 1. test_calculate_status_normal
# ---------------------------------------------------------------------------


async def test_calculate_status_normal(db_session: AsyncSession) -> None:
    """Clock in 08:55, clock out 18:05 -> NORMAL."""
    from app.services.reporting_service import calculate_status

    target_date = datetime.date(2026, 3, 19)
    shift_start = datetime.time(9, 0)
    shift_end = datetime.time(18, 0)
    first_clock_in = datetime.datetime(2026, 3, 19, 8, 55)
    last_clock_out = datetime.datetime(2026, 3, 19, 18, 5)

    status = calculate_status(shift_start, shift_end, first_clock_in, last_clock_out)

    assert status == AttendanceStatus.NORMAL


# ---------------------------------------------------------------------------
# 2. test_calculate_status_late
# ---------------------------------------------------------------------------


async def test_calculate_status_late(db_session: AsyncSession) -> None:
    """Clock in 09:10 (> 09:05 grace) -> LATE."""
    from app.services.reporting_service import calculate_status

    shift_start = datetime.time(9, 0)
    shift_end = datetime.time(18, 0)
    first_clock_in = datetime.datetime(2026, 3, 19, 9, 10)
    last_clock_out = datetime.datetime(2026, 3, 19, 18, 5)

    status = calculate_status(shift_start, shift_end, first_clock_in, last_clock_out)

    assert status == AttendanceStatus.LATE


# ---------------------------------------------------------------------------
# 3. test_calculate_status_early_leave
# ---------------------------------------------------------------------------


async def test_calculate_status_early_leave(db_session: AsyncSession) -> None:
    """Clock in 08:55, clock out 17:30 (< 18:00) -> EARLY_LEAVE."""
    from app.services.reporting_service import calculate_status

    shift_start = datetime.time(9, 0)
    shift_end = datetime.time(18, 0)
    first_clock_in = datetime.datetime(2026, 3, 19, 8, 55)
    last_clock_out = datetime.datetime(2026, 3, 19, 17, 30)

    status = calculate_status(shift_start, shift_end, first_clock_in, last_clock_out)

    assert status == AttendanceStatus.EARLY_LEAVE


# ---------------------------------------------------------------------------
# 4. test_calculate_status_abnormal
# ---------------------------------------------------------------------------


async def test_calculate_status_abnormal(db_session: AsyncSession) -> None:
    """Only one punch (clock-in but no clock-out) -> ABNORMAL."""
    from app.services.reporting_service import calculate_status

    shift_start = datetime.time(9, 0)
    shift_end = datetime.time(18, 0)
    first_clock_in = datetime.datetime(2026, 3, 19, 8, 55)

    status = calculate_status(shift_start, shift_end, first_clock_in, None)

    assert status == AttendanceStatus.ABNORMAL


# ---------------------------------------------------------------------------
# 5. test_calculate_status_no_punches
# ---------------------------------------------------------------------------


async def test_calculate_status_no_punches(db_session: AsyncSession) -> None:
    """No punches at all -> returns None (no summary created)."""
    from app.services.reporting_service import calculate_status

    shift_start = datetime.time(9, 0)
    shift_end = datetime.time(18, 0)

    status = calculate_status(shift_start, shift_end, None, None)

    assert status is None


# ---------------------------------------------------------------------------
# 6. test_first_in_last_out_logic
# ---------------------------------------------------------------------------


@freeze_time("2026-03-19 20:00:00")
async def test_first_in_last_out_logic(db_session: AsyncSession) -> None:
    """3 punches at 08:50, 12:00, 18:10 -> first_clock_in=08:50, last_clock_out=18:10."""
    from app.services.reporting_service import generate_daily_summary

    await _create_employee(db_session, "EMP010")

    target_date = datetime.date(2026, 3, 19)
    await _create_attendance_log(
        db_session, "EMP010", datetime.datetime(2026, 3, 19, 8, 50)
    )
    await _create_attendance_log(
        db_session, "EMP010", datetime.datetime(2026, 3, 19, 12, 0)
    )
    await _create_attendance_log(
        db_session, "EMP010", datetime.datetime(2026, 3, 19, 18, 10)
    )

    summary = await generate_daily_summary(db_session, "EMP010", target_date)

    assert summary is not None
    assert summary.first_clock_in == datetime.datetime(2026, 3, 19, 8, 50)
    assert summary.last_clock_out == datetime.datetime(2026, 3, 19, 18, 10)
    assert summary.status == AttendanceStatus.NORMAL


# ---------------------------------------------------------------------------
# 7. test_grace_period_exactly_5_minutes
# ---------------------------------------------------------------------------


async def test_grace_period_exactly_5_minutes(db_session: AsyncSession) -> None:
    """Clock in at 09:05:00 -> NORMAL, clock in at 09:05:01 -> LATE."""
    from app.services.reporting_service import calculate_status

    shift_start = datetime.time(9, 0)
    shift_end = datetime.time(18, 0)
    last_clock_out = datetime.datetime(2026, 3, 19, 18, 5)

    # Exactly at grace boundary -> NORMAL
    status_at_boundary = calculate_status(
        shift_start,
        shift_end,
        datetime.datetime(2026, 3, 19, 9, 5, 0),
        last_clock_out,
    )
    assert status_at_boundary == AttendanceStatus.NORMAL

    # One second past grace -> LATE
    status_past_boundary = calculate_status(
        shift_start,
        shift_end,
        datetime.datetime(2026, 3, 19, 9, 5, 1),
        last_clock_out,
    )
    assert status_past_boundary == AttendanceStatus.LATE


# ---------------------------------------------------------------------------
# 8. test_generate_daily_summary
# ---------------------------------------------------------------------------


@freeze_time("2026-03-19 20:00:00")
async def test_generate_daily_summary(db_session: AsyncSession) -> None:
    """Creates/upserts a DailyAttendanceSummary record via the service."""
    from app.services.reporting_service import generate_daily_summary

    await _create_employee(db_session, "EMP011")
    target_date = datetime.date(2026, 3, 19)

    await _create_attendance_log(
        db_session, "EMP011", datetime.datetime(2026, 3, 19, 8, 50)
    )
    await _create_attendance_log(
        db_session, "EMP011", datetime.datetime(2026, 3, 19, 18, 10)
    )

    summary = await generate_daily_summary(db_session, "EMP011", target_date)

    assert summary is not None
    assert summary.id is not None
    assert summary.emp_id == "EMP011"
    assert summary.date == target_date
    assert summary.first_clock_in == datetime.datetime(2026, 3, 19, 8, 50)
    assert summary.last_clock_out == datetime.datetime(2026, 3, 19, 18, 10)
    assert summary.status == AttendanceStatus.NORMAL


# ---------------------------------------------------------------------------
# 9. test_generate_summaries_for_all_employees
# ---------------------------------------------------------------------------


@freeze_time("2026-03-19 20:00:00")
async def test_generate_summaries_for_all_employees(
    db_session: AsyncSession,
) -> None:
    """Batch generate summaries for all employees on a date."""
    from app.services.reporting_service import generate_all_summaries

    await _create_employee(db_session, "EMP020", name="Alice", department="Engineering")
    await _create_employee(db_session, "EMP021", name="Bob", department="Sales")
    await _create_employee(db_session, "EMP022", name="Carol", department="Engineering")

    target_date = datetime.date(2026, 3, 19)

    # EMP020 and EMP021 have punches; EMP022 has none
    await _create_attendance_log(
        db_session, "EMP020", datetime.datetime(2026, 3, 19, 8, 55)
    )
    await _create_attendance_log(
        db_session, "EMP020", datetime.datetime(2026, 3, 19, 18, 5)
    )
    await _create_attendance_log(
        db_session, "EMP021", datetime.datetime(2026, 3, 19, 9, 10)
    )
    await _create_attendance_log(
        db_session, "EMP021", datetime.datetime(2026, 3, 19, 18, 0)
    )

    summaries = await generate_all_summaries(db_session, target_date)

    # EMP022 has no punches -> skipped -> only 2 summaries
    assert len(summaries) == 2
    emp_ids = {s.emp_id for s in summaries}
    assert emp_ids == {"EMP020", "EMP021"}


# ---------------------------------------------------------------------------
# 10. test_export_csv_format
# ---------------------------------------------------------------------------


@freeze_time("2026-03-19 20:00:00")
async def test_export_csv_format(db_session: AsyncSession) -> None:
    """Returns CSV string with correct headers."""
    from app.services.reporting_service import export_attendance, generate_daily_summary

    await _create_employee(db_session, "EMP030", name="Alice", department="Engineering")
    target_date = datetime.date(2026, 3, 19)

    await _create_attendance_log(
        db_session, "EMP030", datetime.datetime(2026, 3, 19, 8, 55)
    )
    await _create_attendance_log(
        db_session, "EMP030", datetime.datetime(2026, 3, 19, 18, 5)
    )

    await generate_daily_summary(db_session, "EMP030", target_date)

    csv_output = await export_attendance(
        db_session,
        start_date=target_date,
        end_date=target_date,
        format="csv",
    )

    reader = csv.reader(io.StringIO(csv_output))
    rows = list(reader)

    # Header row
    assert rows[0] == [
        "emp_id",
        "name",
        "department",
        "date",
        "first_clock_in",
        "last_clock_out",
        "status",
    ]
    # Data row
    assert len(rows) == 2
    assert rows[1][0] == "EMP030"
    assert rows[1][1] == "Alice"
    assert rows[1][2] == "Engineering"
    assert rows[1][6] == "NORMAL"


# ---------------------------------------------------------------------------
# 11. test_export_json_format
# ---------------------------------------------------------------------------


@freeze_time("2026-03-19 20:00:00")
async def test_export_json_format(db_session: AsyncSession) -> None:
    """Returns JSON string with correct structure."""
    from app.services.reporting_service import export_attendance, generate_daily_summary

    await _create_employee(db_session, "EMP031", name="Bob", department="Sales")
    target_date = datetime.date(2026, 3, 19)

    await _create_attendance_log(
        db_session, "EMP031", datetime.datetime(2026, 3, 19, 9, 10)
    )
    await _create_attendance_log(
        db_session, "EMP031", datetime.datetime(2026, 3, 19, 18, 5)
    )

    await generate_daily_summary(db_session, "EMP031", target_date)

    json_output = await export_attendance(
        db_session,
        start_date=target_date,
        end_date=target_date,
        format="json",
    )

    data = json.loads(json_output)

    assert isinstance(data, list)
    assert len(data) == 1
    record = data[0]
    assert record["emp_id"] == "EMP031"
    assert record["name"] == "Bob"
    assert record["department"] == "Sales"
    assert record["date"] == "2026-03-19"
    assert record["status"] == "LATE"


# ---------------------------------------------------------------------------
# 12. test_export_date_range_filter
# ---------------------------------------------------------------------------


@freeze_time("2026-03-20 20:00:00")
async def test_export_date_range_filter(db_session: AsyncSession) -> None:
    """Only includes summaries within the requested date range."""
    from app.services.reporting_service import export_attendance, generate_daily_summary

    await _create_employee(db_session, "EMP032", name="Carol", department="Engineering")

    # Create attendance on two different dates
    for day in (18, 19, 20):
        d = datetime.date(2026, 3, day)
        await _create_attendance_log(
            db_session, "EMP032", datetime.datetime(2026, 3, day, 8, 55)
        )
        await _create_attendance_log(
            db_session, "EMP032", datetime.datetime(2026, 3, day, 18, 5)
        )
        await generate_daily_summary(db_session, "EMP032", d)

    # Export only Mar 19-20
    csv_output = await export_attendance(
        db_session,
        start_date=datetime.date(2026, 3, 19),
        end_date=datetime.date(2026, 3, 20),
        format="csv",
    )

    reader = csv.reader(io.StringIO(csv_output))
    rows = list(reader)

    # Header + 2 data rows (Mar 19 and Mar 20 only)
    assert len(rows) == 3
    dates_in_export = {row[3] for row in rows[1:]}
    assert dates_in_export == {"2026-03-19", "2026-03-20"}


# ---------------------------------------------------------------------------
# 13. test_export_department_filter
# ---------------------------------------------------------------------------


@freeze_time("2026-03-19 20:00:00")
async def test_export_department_filter(db_session: AsyncSession) -> None:
    """Filter export by department."""
    from app.services.reporting_service import export_attendance, generate_daily_summary

    await _create_employee(db_session, "EMP040", name="Dave", department="Engineering")
    await _create_employee(db_session, "EMP041", name="Eve", department="Sales")

    target_date = datetime.date(2026, 3, 19)

    for emp_id in ("EMP040", "EMP041"):
        await _create_attendance_log(
            db_session, emp_id, datetime.datetime(2026, 3, 19, 8, 55)
        )
        await _create_attendance_log(
            db_session, emp_id, datetime.datetime(2026, 3, 19, 18, 5)
        )
        await generate_daily_summary(db_session, emp_id, target_date)

    # Export only Engineering
    json_output = await export_attendance(
        db_session,
        start_date=target_date,
        end_date=target_date,
        format="json",
        department="Engineering",
    )

    data = json.loads(json_output)
    assert len(data) == 1
    assert data[0]["emp_id"] == "EMP040"
    assert data[0]["department"] == "Engineering"
