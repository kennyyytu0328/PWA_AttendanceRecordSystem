"""Unit tests for AttendanceLog repository — Phase 2C (TDD)."""

import datetime

import pytest

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.employee import Employee, Role


def _make_employee(emp_id: str = "EMP100", name: str = "Test User") -> Employee:
    """Create a minimal Employee instance for FK satisfaction."""
    return Employee(
        emp_id=emp_id,
        name=name,
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )


def _make_log(
    emp_id: str = "EMP100",
    timestamp: datetime.datetime = datetime.datetime(2026, 3, 19, 9, 0, 0),
    work_mode: WorkMode = WorkMode.OFFICE,
    is_overridden: bool = False,
) -> AttendanceLog:
    """Create a minimal AttendanceLog instance."""
    return AttendanceLog(
        emp_id=emp_id,
        timestamp=timestamp,
        latitude=25.033,
        longitude=121.565,
        accuracy=10.5,
        ip_address="192.168.1.1",
        work_mode=work_mode,
        is_overridden=is_overridden,
    )


# ---------- 1. create_log ----------
async def test_create_attendance_log(db_session):
    """Inserts a log entry and returns it with an auto-generated id."""
    from app.repositories.attendance_repository import create_log

    db_session.add(_make_employee())
    await db_session.commit()

    log = _make_log()
    result = await create_log(db_session, log)

    assert result.id is not None
    assert result.emp_id == "EMP100"
    assert result.timestamp == datetime.datetime(2026, 3, 19, 9, 0, 0)
    assert result.work_mode == WorkMode.OFFICE
    assert result.is_overridden is False


# ---------- 2. find_by_employee_and_date ----------
async def test_find_logs_by_employee_and_date(db_session):
    """Filters logs by emp_id and date range (start of day to end of day)."""
    from app.repositories.attendance_repository import find_by_employee_and_date

    db_session.add(_make_employee())
    await db_session.commit()

    # Two logs on 2026-03-19
    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 19, 9, 0, 0)))
    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 19, 18, 0, 0)))
    # One log on a different day
    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 20, 9, 0, 0)))
    await db_session.commit()

    logs = await find_by_employee_and_date(
        db_session, "EMP100", datetime.date(2026, 3, 19)
    )

    assert len(logs) == 2
    assert all(log.emp_id == "EMP100" for log in logs)


# ---------- 3. find_by_date_range ----------
async def test_find_logs_by_date_range(db_session):
    """Returns all employees' logs within a date range."""
    from app.repositories.attendance_repository import find_by_date_range

    emp_a = _make_employee(emp_id="EMP200", name="Alice")
    emp_b = _make_employee(emp_id="EMP201", name="Bob")
    db_session.add_all([emp_a, emp_b])
    await db_session.commit()

    db_session.add(_make_log(emp_id="EMP200", timestamp=datetime.datetime(2026, 3, 19, 9, 0, 0)))
    db_session.add(_make_log(emp_id="EMP201", timestamp=datetime.datetime(2026, 3, 19, 10, 0, 0)))
    db_session.add(_make_log(emp_id="EMP200", timestamp=datetime.datetime(2026, 3, 20, 9, 0, 0)))
    # Outside range
    db_session.add(_make_log(emp_id="EMP200", timestamp=datetime.datetime(2026, 3, 21, 9, 0, 0)))
    await db_session.commit()

    logs = await find_by_date_range(
        db_session,
        start=datetime.datetime(2026, 3, 19, 0, 0, 0),
        end=datetime.datetime(2026, 3, 21, 0, 0, 0),
    )

    assert len(logs) == 3


# ---------- 4. find_first_clock_in ----------
async def test_find_first_clock_in(db_session):
    """Returns the entry with MIN(timestamp) for employee on a given date."""
    from app.repositories.attendance_repository import find_first_clock_in

    db_session.add(_make_employee())
    await db_session.commit()

    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 19, 8, 55, 0)))
    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 19, 12, 30, 0)))
    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 19, 18, 5, 0)))
    await db_session.commit()

    first = await find_first_clock_in(db_session, "EMP100", datetime.date(2026, 3, 19))

    assert first is not None
    assert first.timestamp == datetime.datetime(2026, 3, 19, 8, 55, 0)


# ---------- 5. find_last_clock_out ----------
async def test_find_last_clock_out(db_session):
    """Returns the entry with MAX(timestamp) for employee on a given date."""
    from app.repositories.attendance_repository import find_last_clock_out

    db_session.add(_make_employee())
    await db_session.commit()

    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 19, 8, 55, 0)))
    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 19, 12, 30, 0)))
    db_session.add(_make_log(timestamp=datetime.datetime(2026, 3, 19, 18, 5, 0)))
    await db_session.commit()

    last = await find_last_clock_out(db_session, "EMP100", datetime.date(2026, 3, 19))

    assert last is not None
    assert last.timestamp == datetime.datetime(2026, 3, 19, 18, 5, 0)


# ---------- 5b. overridden logs must be ignored ----------
async def test_find_first_clock_in_ignores_overridden(db_session):
    """An overridden earlier log must NOT shadow a fresh non-overridden one."""
    from app.repositories.attendance_repository import find_first_clock_in

    db_session.add(_make_employee())
    await db_session.commit()

    # Stale entry (earlier in the day) marked overridden
    db_session.add(
        _make_log(
            timestamp=datetime.datetime(2026, 3, 19, 7, 0, 0),
            is_overridden=True,
        )
    )
    # Current entry — should win
    db_session.add(
        _make_log(
            timestamp=datetime.datetime(2026, 3, 19, 9, 0, 0),
            is_overridden=False,
        )
    )
    await db_session.commit()

    first = await find_first_clock_in(db_session, "EMP100", datetime.date(2026, 3, 19))

    assert first is not None
    assert first.timestamp == datetime.datetime(2026, 3, 19, 9, 0, 0)


async def test_find_last_clock_out_ignores_overridden(db_session):
    """An overridden later log must NOT shadow a fresh non-overridden one.

    Regression test: prior bug where saving a 17:25 clock-out failed to take
    effect because a stale overridden 20:25 log was still being returned by
    MAX(timestamp), then the daily summary rebuilt around the wrong value.
    """
    from app.repositories.attendance_repository import find_last_clock_out

    db_session.add(_make_employee())
    await db_session.commit()

    # Current entry
    db_session.add(
        _make_log(
            timestamp=datetime.datetime(2026, 3, 19, 17, 25, 0),
            is_overridden=False,
        )
    )
    # Stale entry (later in the day) marked overridden — should be ignored
    db_session.add(
        _make_log(
            timestamp=datetime.datetime(2026, 3, 19, 20, 25, 0),
            is_overridden=True,
        )
    )
    await db_session.commit()

    last = await find_last_clock_out(db_session, "EMP100", datetime.date(2026, 3, 19))

    assert last is not None
    assert last.timestamp == datetime.datetime(2026, 3, 19, 17, 25, 0)


# ---------- 6. no update method ----------
async def test_no_update_method_exists(db_session):
    """The attendance repository must NOT expose an update function."""
    import app.repositories.attendance_repository as repo

    assert not hasattr(repo, "update"), "Repository must not have an update function"
    assert not hasattr(repo, "update_log"), "Repository must not have an update_log function"
    assert not hasattr(repo, "delete"), "Repository must not have a delete function"
    assert not hasattr(repo, "delete_log"), "Repository must not have a delete_log function"


# ---------- 7. override creates new entry ----------
async def test_override_creates_new_entry(db_session):
    """Creating a log with is_overridden=True creates a NEW entry, not modifying existing."""
    from app.repositories.attendance_repository import create_log
    from sqlmodel import select

    db_session.add(_make_employee())
    await db_session.commit()

    # Original entry
    original = _make_log(timestamp=datetime.datetime(2026, 3, 19, 9, 0, 0))
    await create_log(db_session, original)

    # Override entry — a separate NEW record
    override = _make_log(
        timestamp=datetime.datetime(2026, 3, 19, 8, 50, 0),
        is_overridden=True,
    )
    await create_log(db_session, override)

    # Both entries must exist
    result = await db_session.execute(
        select(AttendanceLog).where(AttendanceLog.emp_id == "EMP100")
    )
    rows = result.scalars().all()

    assert len(rows) == 2
    overridden_rows = [r for r in rows if r.is_overridden is True]
    normal_rows = [r for r in rows if r.is_overridden is False]
    assert len(overridden_rows) == 1
    assert len(normal_rows) == 1
    assert overridden_rows[0].id != normal_rows[0].id
