"""Summary repository — async data-access functions for DailyAttendanceSummary."""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary


async def create_summary(
    session: AsyncSession, summary: DailyAttendanceSummary
) -> DailyAttendanceSummary:
    """Persist a new daily attendance summary and return the refreshed instance."""
    session.add(summary)
    await session.commit()
    await session.refresh(summary)
    return summary


async def upsert_summary(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
    first_clock_in: datetime.datetime | None,
    last_clock_out: datetime.datetime | None,
    status: AttendanceStatus,
) -> DailyAttendanceSummary:
    """Insert or update a daily attendance summary by (emp_id, date).

    If a row with the given (emp_id, date) already exists, update its
    fields. Otherwise create a new row. Returns the persisted instance.
    """
    statement = select(DailyAttendanceSummary).where(
        DailyAttendanceSummary.emp_id == emp_id,
        DailyAttendanceSummary.date == date,
    )
    result = await session.execute(statement)
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.first_clock_in = first_clock_in
        existing.last_clock_out = last_clock_out
        existing.status = status
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    summary = DailyAttendanceSummary(
        emp_id=emp_id,
        date=date,
        first_clock_in=first_clock_in,
        last_clock_out=last_clock_out,
        status=status,
    )
    session.add(summary)
    await session.commit()
    await session.refresh(summary)
    return summary


async def find_by_id(
    session: AsyncSession, summary_id: int
) -> DailyAttendanceSummary | None:
    """Return a summary by primary key, or None."""
    statement = select(DailyAttendanceSummary).where(
        DailyAttendanceSummary.id == summary_id
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def find_by_employee(
    session: AsyncSession,
    emp_id: str,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> list[DailyAttendanceSummary]:
    """Return summaries for an employee, optionally filtered by date range."""
    statement = select(DailyAttendanceSummary).where(
        DailyAttendanceSummary.emp_id == emp_id
    )

    if start_date is not None:
        statement = statement.where(DailyAttendanceSummary.date >= start_date)

    if end_date is not None:
        statement = statement.where(DailyAttendanceSummary.date <= end_date)

    result = await session.execute(statement)
    return list(result.scalars().all())


async def find_by_date(
    session: AsyncSession, date: datetime.date
) -> list[DailyAttendanceSummary]:
    """Return all employee summaries for a specific date."""
    statement = select(DailyAttendanceSummary).where(
        DailyAttendanceSummary.date == date
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def find_by_status(
    session: AsyncSession, status: AttendanceStatus
) -> list[DailyAttendanceSummary]:
    """Return all summaries matching the given attendance status."""
    statement = select(DailyAttendanceSummary).where(
        DailyAttendanceSummary.status == status
    )
    result = await session.execute(statement)
    return list(result.scalars().all())
