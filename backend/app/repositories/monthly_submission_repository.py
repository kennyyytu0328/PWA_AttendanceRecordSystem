"""Monthly submission repository — async data access."""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monthly_submission import MonthlySubmission


async def upsert(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> MonthlySubmission:
    """Insert or refresh the (emp_id, year, month) row's submitted_at."""
    statement = select(MonthlySubmission).where(
        MonthlySubmission.emp_id == emp_id,
        MonthlySubmission.year == year,
        MonthlySubmission.month == month,
    )
    result = await session.execute(statement)
    existing = result.scalar_one_or_none()

    now = datetime.datetime.now(datetime.UTC)

    if existing is not None:
        existing.submitted_at = now
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    row = MonthlySubmission(
        emp_id=emp_id, year=year, month=month, submitted_at=now
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def find(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> MonthlySubmission | None:
    """Return the submission row for (emp_id, year, month) or None."""
    statement = select(MonthlySubmission).where(
        MonthlySubmission.emp_id == emp_id,
        MonthlySubmission.year == year,
        MonthlySubmission.month == month,
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def submitted_emp_ids(
    session: AsyncSession,
    year: int,
    month: int,
) -> set[str]:
    """Return the set of emp_ids that have submitted for the given (year, month)."""
    statement = select(MonthlySubmission.emp_id).where(
        MonthlySubmission.year == year,
        MonthlySubmission.month == month,
    )
    result = await session.execute(statement)
    return set(result.scalars().all())


async def list_by_month(
    session: AsyncSession,
    year: int,
    month: int,
) -> list[MonthlySubmission]:
    """Return all submission rows for (year, month), ordered by emp_id."""
    statement = (
        select(MonthlySubmission)
        .where(
            MonthlySubmission.year == year,
            MonthlySubmission.month == month,
        )
        .order_by(MonthlySubmission.emp_id)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())
