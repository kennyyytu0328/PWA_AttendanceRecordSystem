"""Monthly submission service — thin layer over monthly_submission_repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monthly_submission import MonthlySubmission
from app.repositories import monthly_submission_repository


async def submit_month(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> MonthlySubmission:
    """Upsert the (emp_id, year, month) row, refreshing submitted_at."""
    return await monthly_submission_repository.upsert(
        session, emp_id=emp_id, year=year, month=month
    )


async def is_submitted(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> bool:
    row = await monthly_submission_repository.find(
        session, emp_id=emp_id, year=year, month=month
    )
    return row is not None


async def get_status(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> MonthlySubmission | None:
    return await monthly_submission_repository.find(
        session, emp_id=emp_id, year=year, month=month
    )
