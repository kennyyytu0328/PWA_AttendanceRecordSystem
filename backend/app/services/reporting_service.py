"""Reporting service — First-In-Last-Out attendance logic, summary generation, and export.

Provides:
- ``calculate_status``: pure function that classifies a day as NORMAL / LATE /
  EARLY_LEAVE / ABNORMAL based on shift times and clock-in/out timestamps.
- ``generate_daily_summary``: builds (or upserts) a single employee's daily summary.
- ``generate_all_summaries``: batch-generates summaries for every employee on a date.
- ``export_attendance``: exports summary data as CSV or JSON, with optional filters.
"""

import csv
import datetime
import io
import json
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary
from app.repositories import attendance_repository, employee_repository, summary_repository
from app.repositories import system_config_repository

DEFAULT_GRACE_MINUTES = 5


def calculate_status(
    shift_start: datetime.time,
    shift_end: datetime.time,
    first_clock_in: datetime.datetime | None,
    last_clock_out: datetime.datetime | None,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> AttendanceStatus | None:
    """Determine the attendance status for a single day.

    Parameters
    ----------
    shift_start:
        The employee's scheduled start time.
    shift_end:
        The employee's scheduled end time.
    first_clock_in:
        Earliest punch of the day, or ``None`` if no punches.
    last_clock_out:
        Latest punch of the day, or ``None`` if no punches.

    Returns
    -------
    AttendanceStatus | None
        ``None`` when there are no punches at all.
        ``ABNORMAL`` when only one of clock-in / clock-out exists.
        ``LATE`` when clock-in exceeds the grace period (takes precedence).
        ``EARLY_LEAVE`` when clock-out is before shift end.
        ``NORMAL`` otherwise.
    """
    if first_clock_in is None and last_clock_out is None:
        return None

    if first_clock_in is None or last_clock_out is None:
        return AttendanceStatus.ABNORMAL

    # Calculate grace deadline: shift_start + grace period
    # Use a reference date to combine time + timedelta
    reference_date = first_clock_in.date()
    grace_deadline = (
        datetime.datetime.combine(reference_date, shift_start)
        + timedelta(minutes=grace_minutes)
    ).time()

    is_late = first_clock_in.time() > grace_deadline

    # Only one punch exists — still check for lateness so the employee
    # can submit a reason immediately after a late clock-in.
    # A single on-time punch is a normal clock-in (not yet clocked out).
    if first_clock_in == last_clock_out:
        return AttendanceStatus.LATE if is_late else AttendanceStatus.NORMAL

    is_early_leave = last_clock_out.time() < shift_end

    if is_late and is_early_leave:
        return AttendanceStatus.LATE_AND_EARLY_LEAVE

    if is_late:
        return AttendanceStatus.LATE

    if is_early_leave:
        return AttendanceStatus.EARLY_LEAVE

    return AttendanceStatus.NORMAL


async def generate_daily_summary(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
) -> DailyAttendanceSummary | None:
    """Build or upsert a daily attendance summary for one employee.

    Returns ``None`` if the employee has no attendance logs on *date*.
    """
    employee = await employee_repository.find_by_id(session, emp_id)
    if employee is None:
        return None

    first_log = await attendance_repository.find_first_clock_in(session, emp_id, date)
    last_log = await attendance_repository.find_last_clock_out(session, emp_id, date)

    first_clock_in = first_log.timestamp if first_log is not None else None
    last_clock_out = last_log.timestamp if last_log is not None else None

    grace_minutes = await system_config_repository.get_grace_period(session)
    status = calculate_status(
        employee.shift_start_time,
        employee.shift_end_time,
        first_clock_in,
        last_clock_out,
        grace_minutes=grace_minutes,
    )

    if status is None:
        return None

    summary = await summary_repository.upsert_summary(
        session,
        emp_id=emp_id,
        date=date,
        first_clock_in=first_clock_in,
        last_clock_out=last_clock_out,
        status=status,
    )

    return summary


async def generate_all_summaries(
    session: AsyncSession,
    date: datetime.date,
) -> list[DailyAttendanceSummary]:
    """Generate daily summaries for every employee on *date*.

    Employees with no punches are silently skipped.
    """
    employees = await employee_repository.find_all(session, skip=0, limit=10000)

    summaries: list[DailyAttendanceSummary] = []
    for emp in employees:
        summary = await generate_daily_summary(session, emp.emp_id, date)
        if summary is not None:
            summaries.append(summary)

    return summaries


async def get_daily_report(
    session: AsyncSession,
    start_date: datetime.date,
    end_date: datetime.date | None = None,
    department: str | None = None,
    emp_id: str | None = None,
    status_filter: str | None = None,
) -> list[DailyAttendanceSummary]:
    """Return daily attendance summaries for a date range (inclusive).

    Parameters
    ----------
    session:
        The async database session.
    start_date:
        The first date to retrieve summaries for.
    end_date:
        The last date (inclusive). Defaults to *start_date* if ``None``.
    department:
        Optional department filter.
    emp_id:
        Optional individual employee filter.
    status_filter:
        Optional status filter (e.g. ``"LATE"``).

    Returns
    -------
    list[DailyAttendanceSummary]
        Matching summaries, sorted by date then emp_id.
    """
    if end_date is None:
        end_date = start_date

    all_summaries: list[DailyAttendanceSummary] = []
    current = start_date
    while current <= end_date:
        day_summaries = await generate_all_summaries(session, current)
        all_summaries.extend(day_summaries)
        current += datetime.timedelta(days=1)

    if emp_id is not None:
        all_summaries = [s for s in all_summaries if s.emp_id == emp_id]

    if department is not None:
        employees = await employee_repository.find_by_department(session, department)
        dept_emp_ids = {emp.emp_id for emp in employees}
        all_summaries = [s for s in all_summaries if s.emp_id in dept_emp_ids]

    if status_filter is not None:
        try:
            target_status = AttendanceStatus(status_filter)
        except ValueError:
            return []
        all_summaries = [s for s in all_summaries if s.status == target_status]

    all_summaries.sort(key=lambda s: (s.date, s.emp_id))
    return all_summaries


async def export_attendance(
    session: AsyncSession,
    start_date: datetime.date,
    end_date: datetime.date,
    format: str,
    department: str | None = None,
    emp_id: str | None = None,
) -> str | bytes:
    """Export attendance summaries as CSV, JSON, or Excel.

    Parameters
    ----------
    session:
        The async database session.
    start_date:
        Start of the date range (inclusive).
    end_date:
        End of the date range (inclusive).
    format:
        ``"csv"``, ``"json"``, or ``"xlsx"``.
    department:
        Optional department filter.
    emp_id:
        Optional individual employee filter.

    Returns
    -------
    str | bytes
        Formatted string (CSV/JSON) or bytes (xlsx).
    """
    # Determine which employees to include
    if emp_id is not None:
        emp = await employee_repository.find_by_id(session, emp_id)
        employees = [emp] if emp is not None else []
    elif department is not None:
        employees = await employee_repository.find_by_department(session, department)
    else:
        employees = await employee_repository.find_all(session, skip=0, limit=10000)

    emp_map = {emp.emp_id: emp for emp in employees}

    # Gather all summaries across the date range for matching employees
    all_summaries: list[DailyAttendanceSummary] = []
    for emp in employees:
        summaries = await summary_repository.find_by_employee(
            session,
            emp.emp_id,
            start_date=start_date,
            end_date=end_date,
        )
        all_summaries.extend(summaries)

    # Sort by date then emp_id for deterministic output
    all_summaries.sort(key=lambda s: (s.date, s.emp_id))

    # Build row dicts
    headers = [
        "emp_id",
        "name",
        "department",
        "date",
        "first_clock_in",
        "last_clock_out",
        "status",
    ]

    rows: list[dict[str, str]] = []
    for s in all_summaries:
        emp = emp_map.get(s.emp_id)
        rows.append({
            "emp_id": s.emp_id,
            "name": emp.name if emp else "",
            "department": emp.department if emp else "",
            "date": s.date.isoformat(),
            "first_clock_in": (
                s.first_clock_in.isoformat() if s.first_clock_in else ""
            ),
            "last_clock_out": (
                s.last_clock_out.isoformat() if s.last_clock_out else ""
            ),
            "status": s.status.value,
        })

    if format == "json":
        return json.dumps(rows, ensure_ascii=False)

    if format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance Report"

        # Header row
        bold_font = Font(bold=True)
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = bold_font

        # Data rows
        for row_idx, row in enumerate(rows, 2):
            for col_idx, header in enumerate(headers, 1):
                ws.cell(row=row_idx, column=col_idx, value=row[header])

        # Auto-size columns
        for col_idx, header in enumerate(headers, 1):
            max_len = len(header)
            for row in rows:
                max_len = max(max_len, len(str(row[header])))
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max_len + 2

        ws.auto_filter.ref = ws.dimensions

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    # Default: CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row[h] for h in headers])

    return output.getvalue()
