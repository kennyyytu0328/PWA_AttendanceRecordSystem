"""Monthly submission service — thin layer over monthly_submission_repository."""

import calendar as _calendar
import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monthly_submission import MonthlySubmission
from app.repositories import (
    attendance_repository,
    employee_repository,
    monthly_submission_repository,
    summary_repository,
    system_config_repository,
)
from app.services.reporting_service import _load_calendar_for_year, generate_daily_summary
from app.utils.taiwan_calendar import DayKind, classify_date_kind

_REQUIRED_DAY_KINDS = frozenset({DayKind.WORKDAY, DayKind.MAKEUP_WORKDAY})


async def find_missing_late_reason_dates(
    session: AsyncSession, emp_id: str, year: int, month: int
) -> list[datetime.date]:
    """Workdays whose last clock-out runs past shift end without a reason.

    Mirrors the frontend rule exactly: workday-kind days only, strict
    ``time > shift_end``, single-punch days exempt (no clock-out yet — #16),
    leave days exempt unless the leave type is in the configured
    still-requires list (e.g. 出差).
    """
    employee = await employee_repository.find_by_id(session, emp_id)
    if employee is None:
        return []
    required_leave_types = set(
        await system_config_repository.get_late_reason_required_leave_types(session)
    )
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, _calendar.monthrange(year, month)[1])
    calendar_data = await _load_calendar_for_year(session, year)

    # Summaries are materialized lazily (report/page loads), so a workday whose
    # month was never opened in the UI may have punches but no summary row.
    # Regenerate summaries for every workday-kind date carrying a live punch
    # before scanning — otherwise a direct API submission bypasses this gate.
    month_start = datetime.datetime.combine(first, datetime.time.min)
    month_end = datetime.datetime.combine(
        last + datetime.timedelta(days=1), datetime.time.min
    )
    logs = await attendance_repository.find_by_date_range_and_emp_ids(
        session, month_start, month_end, {emp_id}
    )
    punch_dates = {
        log.timestamp.date() for log in logs if not log.is_overridden
    }
    for punch_date in sorted(punch_dates):
        day_kind = classify_date_kind(calendar_data, punch_date)
        if day_kind not in _REQUIRED_DAY_KINDS:
            continue
        await generate_daily_summary(session, emp_id, punch_date, day_kind=day_kind)

    summaries = await summary_repository.find_by_employee(
        session, emp_id, start_date=first, end_date=last
    )

    missing: list[datetime.date] = []
    for s in summaries:
        if classify_date_kind(calendar_data, s.date) not in _REQUIRED_DAY_KINDS:
            continue
        if s.leave_type and s.leave_type not in required_leave_types:
            continue
        if s.first_clock_in is None or s.last_clock_out is None:
            continue
        if s.first_clock_in == s.last_clock_out:
            continue
        # Truncate to minute precision so the rule matches what the UI shows
        # (frontend compares "HH:MM" strings): a 17:30:22 clock-out against a
        # 17:30 shift end is on time, not "late without a reason".
        clock_out = s.last_clock_out.time().replace(second=0, microsecond=0)
        if clock_out <= employee.shift_end_time:
            continue
        if s.late_leave_reason:
            continue
        missing.append(s.date)
    return sorted(missing)


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
