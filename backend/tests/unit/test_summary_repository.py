"""Unit tests for Summary Repository — Phase 2E (TDD)."""

import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary
from app.models.employee import Employee, Role
from app.repositories.summary_repository import (
    create_summary,
    find_by_date,
    find_by_employee,
    find_by_status,
    upsert_summary,
)


async def _create_employee(
    session: AsyncSession, emp_id: str = "EMP001"
) -> Employee:
    """Helper: insert an employee so FK constraints are satisfied."""
    emp = Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    session.add(emp)
    await session.commit()
    return emp


# ---------- 1. test_create_summary ----------


async def test_create_summary(db_session: AsyncSession) -> None:
    """Creates a daily summary and returns it with an auto-generated id."""
    await _create_employee(db_session, "EMP001")

    summary = DailyAttendanceSummary(
        emp_id="EMP001",
        date=datetime.date(2026, 3, 19),
        first_clock_in=datetime.datetime(2026, 3, 19, 9, 0),
        last_clock_out=datetime.datetime(2026, 3, 19, 18, 0),
        status=AttendanceStatus.NORMAL,
    )

    result = await create_summary(db_session, summary)

    assert result.id is not None
    assert result.emp_id == "EMP001"
    assert result.date == datetime.date(2026, 3, 19)
    assert result.first_clock_in == datetime.datetime(2026, 3, 19, 9, 0)
    assert result.last_clock_out == datetime.datetime(2026, 3, 19, 18, 0)
    assert result.status == AttendanceStatus.NORMAL


# ---------- 2. test_upsert_summary ----------


async def test_upsert_summary(db_session: AsyncSession) -> None:
    """Upsert inserts when (emp_id, date) is new, updates when it exists."""
    await _create_employee(db_session, "EMP002")

    # --- Insert path: no existing row for (EMP002, 2026-03-19) ---
    inserted = await upsert_summary(
        db_session,
        emp_id="EMP002",
        date=datetime.date(2026, 3, 19),
        first_clock_in=datetime.datetime(2026, 3, 19, 9, 5),
        last_clock_out=None,
        status=AttendanceStatus.LATE,
    )

    assert inserted.id is not None
    assert inserted.emp_id == "EMP002"
    assert inserted.date == datetime.date(2026, 3, 19)
    assert inserted.first_clock_in == datetime.datetime(2026, 3, 19, 9, 5)
    assert inserted.last_clock_out is None
    assert inserted.status == AttendanceStatus.LATE

    original_id = inserted.id

    # --- Update path: same (emp_id, date), different data ---
    updated = await upsert_summary(
        db_session,
        emp_id="EMP002",
        date=datetime.date(2026, 3, 19),
        first_clock_in=datetime.datetime(2026, 3, 19, 9, 5),
        last_clock_out=datetime.datetime(2026, 3, 19, 17, 30),
        status=AttendanceStatus.EARLY_LEAVE,
    )

    assert updated.id == original_id  # same row was updated
    assert updated.last_clock_out == datetime.datetime(2026, 3, 19, 17, 30)
    assert updated.status == AttendanceStatus.EARLY_LEAVE


# ---------- 3. test_find_summaries_by_employee ----------


async def test_find_summaries_by_employee(db_session: AsyncSession) -> None:
    """Filter summaries by emp_id and optional date range."""
    await _create_employee(db_session, "EMP003")

    dates = [
        datetime.date(2026, 3, 17),
        datetime.date(2026, 3, 18),
        datetime.date(2026, 3, 19),
        datetime.date(2026, 3, 20),
    ]
    for d in dates:
        summary = DailyAttendanceSummary(
            emp_id="EMP003",
            date=d,
            first_clock_in=datetime.datetime(d.year, d.month, d.day, 9, 0),
            last_clock_out=datetime.datetime(d.year, d.month, d.day, 18, 0),
            status=AttendanceStatus.NORMAL,
        )
        await create_summary(db_session, summary)

    # All summaries for EMP003
    all_results = await find_by_employee(db_session, "EMP003")
    assert len(all_results) == 4

    # With start_date only
    from_18 = await find_by_employee(
        db_session, "EMP003", start_date=datetime.date(2026, 3, 18)
    )
    assert len(from_18) == 3
    assert all(r.date >= datetime.date(2026, 3, 18) for r in from_18)

    # With end_date only
    until_19 = await find_by_employee(
        db_session, "EMP003", end_date=datetime.date(2026, 3, 19)
    )
    assert len(until_19) == 3
    assert all(r.date <= datetime.date(2026, 3, 19) for r in until_19)

    # With both start_date and end_date
    range_results = await find_by_employee(
        db_session,
        "EMP003",
        start_date=datetime.date(2026, 3, 18),
        end_date=datetime.date(2026, 3, 19),
    )
    assert len(range_results) == 2
    assert all(
        datetime.date(2026, 3, 18) <= r.date <= datetime.date(2026, 3, 19)
        for r in range_results
    )


# ---------- 4. test_find_summaries_by_date ----------


async def test_find_summaries_by_date(db_session: AsyncSession) -> None:
    """All employee summaries for a specific date."""
    await _create_employee(db_session, "EMP004")
    await _create_employee(db_session, "EMP005")
    await _create_employee(db_session, "EMP006")

    target_date = datetime.date(2026, 3, 19)
    other_date = datetime.date(2026, 3, 18)

    for emp_id in ("EMP004", "EMP005", "EMP006"):
        await create_summary(
            db_session,
            DailyAttendanceSummary(
                emp_id=emp_id,
                date=target_date,
                first_clock_in=datetime.datetime(2026, 3, 19, 9, 0),
                last_clock_out=datetime.datetime(2026, 3, 19, 18, 0),
                status=AttendanceStatus.NORMAL,
            ),
        )

    # Add one summary on a different date
    await create_summary(
        db_session,
        DailyAttendanceSummary(
            emp_id="EMP004",
            date=other_date,
            first_clock_in=datetime.datetime(2026, 3, 18, 9, 0),
            last_clock_out=datetime.datetime(2026, 3, 18, 18, 0),
            status=AttendanceStatus.NORMAL,
        ),
    )

    results = await find_by_date(db_session, target_date)

    assert len(results) == 3
    emp_ids = {r.emp_id for r in results}
    assert emp_ids == {"EMP004", "EMP005", "EMP006"}
    assert all(r.date == target_date for r in results)


# ---------- 5. test_find_summaries_by_status ----------


async def test_find_summaries_by_status(db_session: AsyncSession) -> None:
    """Filter summaries by AttendanceStatus."""
    await _create_employee(db_session, "EMP007")
    await _create_employee(db_session, "EMP008")
    await _create_employee(db_session, "EMP009")

    await create_summary(
        db_session,
        DailyAttendanceSummary(
            emp_id="EMP007",
            date=datetime.date(2026, 3, 19),
            first_clock_in=datetime.datetime(2026, 3, 19, 9, 10),
            last_clock_out=datetime.datetime(2026, 3, 19, 18, 0),
            status=AttendanceStatus.LATE,
        ),
    )
    await create_summary(
        db_session,
        DailyAttendanceSummary(
            emp_id="EMP008",
            date=datetime.date(2026, 3, 19),
            first_clock_in=datetime.datetime(2026, 3, 19, 9, 15),
            last_clock_out=datetime.datetime(2026, 3, 19, 18, 0),
            status=AttendanceStatus.LATE,
        ),
    )
    await create_summary(
        db_session,
        DailyAttendanceSummary(
            emp_id="EMP009",
            date=datetime.date(2026, 3, 19),
            first_clock_in=datetime.datetime(2026, 3, 19, 9, 0),
            last_clock_out=datetime.datetime(2026, 3, 19, 18, 0),
            status=AttendanceStatus.NORMAL,
        ),
    )

    late_results = await find_by_status(db_session, AttendanceStatus.LATE)

    assert len(late_results) == 2
    assert all(r.status == AttendanceStatus.LATE for r in late_results)
    emp_ids = {r.emp_id for r in late_results}
    assert emp_ids == {"EMP007", "EMP008"}

    normal_results = await find_by_status(db_session, AttendanceStatus.NORMAL)
    assert len(normal_results) == 1
    assert normal_results[0].emp_id == "EMP009"


# ---------- 6. test_upsert_summary_persists_leave_type_and_remark ----------


async def test_upsert_summary_persists_leave_type_and_remark(db_session):
    # Use the _create_employee helper already in this file
    await _create_employee(db_session, emp_id="E010")
    summary = await upsert_summary(
        db_session,
        emp_id="E010",
        date=datetime.date(2026, 5, 14),
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休",
        remark="上午",
    )
    assert summary.leave_type == "特休"
    assert summary.remark == "上午"


# ---------- 7. test_upsert_summary_updates_remark_fields_on_existing_row ----------


async def test_upsert_summary_updates_remark_fields_on_existing_row(db_session):
    await _create_employee(db_session, emp_id="E011")
    await upsert_summary(
        db_session,
        emp_id="E011",
        date=datetime.date(2026, 5, 14),
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.ABSENT,
    )
    updated = await upsert_summary(
        db_session,
        emp_id="E011",
        date=datetime.date(2026, 5, 14),
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="病假",
        remark=None,
    )
    assert updated.status == AttendanceStatus.LEAVE
    assert updated.leave_type == "病假"
    assert updated.remark is None
