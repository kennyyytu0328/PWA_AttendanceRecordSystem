"""Reason service — business logic for late/early-leave reason submissions."""

import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_reason import AttendanceReason
from app.models.daily_attendance_summary import AttendanceStatus
from app.repositories import reason_repository, summary_repository


async def submit_reason(
    session: AsyncSession,
    emp_id: str,
    summary_id: int,
    reason_text: str,
) -> AttendanceReason:
    """Submit a reason for a LATE or EARLY_LEAVE daily summary.

    Raises
    ------
    ValueError
        If the summary doesn't exist, doesn't belong to the employee,
        the status isn't LATE or EARLY_LEAVE, or a reason already exists.
    """
    summary = await summary_repository.find_by_id(session, summary_id)
    if summary is None:
        raise ValueError("Summary not found")

    if summary.emp_id != emp_id:
        raise ValueError("Summary does not belong to this employee")

    allowed = (AttendanceStatus.LATE, AttendanceStatus.EARLY_LEAVE, AttendanceStatus.LATE_AND_EARLY_LEAVE)
    if summary.status not in allowed:
        raise ValueError("Reason can only be submitted for LATE or EARLY_LEAVE status")

    existing = await reason_repository.find_by_summary_id(session, summary_id)
    if existing is not None:
        raise ValueError("Reason already submitted for this summary")

    reason = AttendanceReason(
        summary_id=summary_id,
        emp_id=emp_id,
        reason=reason_text,
    )

    return await reason_repository.create_reason(session, reason)


async def get_reasons_for_employee(
    session: AsyncSession,
    emp_id: str,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> list[AttendanceReason]:
    """Return all reasons submitted by an employee."""
    return await reason_repository.find_by_employee(
        session, emp_id, start_date, end_date
    )


async def get_reason_for_summary(
    session: AsyncSession,
    summary_id: int,
) -> AttendanceReason | None:
    """Return the reason for a specific summary, or None."""
    return await reason_repository.find_by_summary_id(session, summary_id)
