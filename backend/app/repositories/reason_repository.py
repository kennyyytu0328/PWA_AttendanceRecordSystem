"""Attendance reason repository — async data-access functions."""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_reason import AttendanceReason


async def create_reason(
    session: AsyncSession,
    reason: AttendanceReason,
) -> AttendanceReason:
    """Persist a new attendance reason."""
    session.add(reason)
    await session.commit()
    await session.refresh(reason)
    return reason


async def find_by_summary_id(
    session: AsyncSession,
    summary_id: int,
) -> AttendanceReason | None:
    """Return the reason for a specific daily summary, or None."""
    statement = select(AttendanceReason).where(
        AttendanceReason.summary_id == summary_id
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def find_by_employee(
    session: AsyncSession,
    emp_id: str,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> list[AttendanceReason]:
    """Return all reasons for an employee, optionally filtered by date range."""
    statement = select(AttendanceReason).where(
        AttendanceReason.emp_id == emp_id
    )
    if start_date is not None:
        start_dt = datetime.datetime.combine(start_date, datetime.time.min)
        statement = statement.where(AttendanceReason.created_at >= start_dt)
    if end_date is not None:
        end_dt = datetime.datetime.combine(
            end_date + datetime.timedelta(days=1), datetime.time.min
        )
        statement = statement.where(AttendanceReason.created_at < end_dt)
    statement = statement.order_by(AttendanceReason.created_at.desc())
    result = await session.execute(statement)
    return list(result.scalars().all())
