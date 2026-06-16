"""Attendance log repository — immutable, append-only operations.

This module deliberately omits update and delete functions.
Attendance logs are an immutable event stream; corrections are made
by appending new entries with ``is_overridden=True``.
"""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog
from app.models.employee import Employee


async def create_log(
    session: AsyncSession,
    log: AttendanceLog,
) -> AttendanceLog:
    """Persist a new attendance log entry and return it with its generated id."""
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def find_by_employee_and_date(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
) -> list[AttendanceLog]:
    """Return all logs for *emp_id* on the given calendar *date*."""
    start_of_day = datetime.datetime.combine(date, datetime.time.min)
    next_day = datetime.datetime.combine(
        date + datetime.timedelta(days=1), datetime.time.min
    )

    stmt = (
        select(AttendanceLog)
        .where(AttendanceLog.emp_id == emp_id)
        .where(AttendanceLog.timestamp >= start_of_day)
        .where(AttendanceLog.timestamp < next_day)
        .order_by(AttendanceLog.timestamp.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_by_date_range(
    session: AsyncSession,
    start: datetime.datetime,
    end: datetime.datetime,
) -> list[AttendanceLog]:
    """Return all logs (any employee) where ``start <= timestamp < end``."""
    stmt = (
        select(AttendanceLog)
        .where(AttendanceLog.timestamp >= start)
        .where(AttendanceLog.timestamp < end)
        .order_by(AttendanceLog.timestamp.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_by_date_range_and_emp_ids(
    session: AsyncSession,
    start: datetime.datetime,
    end: datetime.datetime,
    emp_ids: set[str],
) -> list[AttendanceLog]:
    """Return logs for the given emp_ids where ``start <= timestamp < end``.

    Used for subtree-scoped team views (Phase 15E). An empty set yields no rows.
    """
    if not emp_ids:
        return []
    stmt = (
        select(AttendanceLog)
        .where(AttendanceLog.timestamp >= start)
        .where(AttendanceLog.timestamp < end)
        .where(AttendanceLog.emp_id.in_(emp_ids))
        .order_by(AttendanceLog.timestamp.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_by_date_range_and_department(
    session: AsyncSession,
    start: datetime.datetime,
    end: datetime.datetime,
    department: str,
) -> list[AttendanceLog]:
    """Return logs for employees in *department* where ``start <= timestamp < end``."""
    stmt = (
        select(AttendanceLog)
        .join(Employee, AttendanceLog.emp_id == Employee.emp_id)
        .where(AttendanceLog.timestamp >= start)
        .where(AttendanceLog.timestamp < end)
        .where(Employee.department == department)
        .order_by(AttendanceLog.timestamp.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_first_clock_in(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
) -> AttendanceLog | None:
    """Return the earliest non-overridden log entry for *emp_id* on the given *date*."""
    start_of_day = datetime.datetime.combine(date, datetime.time.min)
    next_day = datetime.datetime.combine(
        date + datetime.timedelta(days=1), datetime.time.min
    )

    stmt = (
        select(AttendanceLog)
        .where(AttendanceLog.emp_id == emp_id)
        .where(AttendanceLog.timestamp >= start_of_day)
        .where(AttendanceLog.timestamp < next_day)
        .where(AttendanceLog.is_overridden == False)  # noqa: E712
        .order_by(AttendanceLog.timestamp.asc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def find_last_clock_out(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
) -> AttendanceLog | None:
    """Return the latest non-overridden log entry for *emp_id* on the given *date*."""
    start_of_day = datetime.datetime.combine(date, datetime.time.min)
    next_day = datetime.datetime.combine(
        date + datetime.timedelta(days=1), datetime.time.min
    )

    stmt = (
        select(AttendanceLog)
        .where(AttendanceLog.emp_id == emp_id)
        .where(AttendanceLog.timestamp >= start_of_day)
        .where(AttendanceLog.timestamp < next_day)
        .where(AttendanceLog.is_overridden == False)  # noqa: E712
        .order_by(AttendanceLog.timestamp.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def mark_overridden_by_employee_and_date(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
) -> int:
    """Mark all non-overridden logs for an employee on a date as overridden.

    Returns the count of updated rows. This is the ONE exception to immutability:
    we flip is_overridden=True on old entries, but never delete or modify content.
    """
    from sqlalchemy import update

    start = datetime.datetime.combine(date, datetime.time.min)
    end = datetime.datetime.combine(date, datetime.time.max)
    stmt = (
        update(AttendanceLog)
        .where(
            AttendanceLog.emp_id == emp_id,
            AttendanceLog.timestamp >= start,
            AttendanceLog.timestamp <= end,
            AttendanceLog.is_overridden == False,  # noqa: E712
        )
        .values(is_overridden=True)
    )
    result = await session.execute(stmt)
    return result.rowcount
