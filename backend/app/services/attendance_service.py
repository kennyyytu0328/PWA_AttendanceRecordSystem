"""Attendance service — punch workflow and override logic.

Orchestrates the clock-in/out flow: employee validation, geolocation-based
work-mode determination, immutable log creation, and manager overrides.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.repositories import attendance_repository, employee_repository, system_config_repository
from app.services import geolocation_service
from app.services.permission_service import APPROVE_OVERRIDE, has_permission

__all__ = [
    "PunchResult",
    "get_all_logs",
    "get_history",
    "get_team_logs",
    "get_today_punches",
    "override_attendance",
    "punch",
]


@dataclass(frozen=True)
class PunchResult:
    """Immutable result of a punch operation."""

    log: AttendanceLog
    work_mode: WorkMode
    distance_km: float
    is_low_accuracy: bool
    tardiness_status: AttendanceStatus | None = None
    summary_id: int | None = None


async def punch(
    session: AsyncSession,
    emp_id: str,
    latitude: float,
    longitude: float,
    accuracy: float,
    ip_address: str,
) -> PunchResult:
    """Record a clock-in/out punch for *emp_id*.

    1. Verify employee exists.
    2. Determine work mode via geolocation service.
    3. Create an immutable AttendanceLog entry.
    4. Return a PunchResult with metadata.

    Raises
    ------
    ValueError
        If *emp_id* does not correspond to an existing employee.
    """
    employee = await employee_repository.find_by_id(session, emp_id)
    if employee is None:
        raise ValueError(f"Employee '{emp_id}' not found")

    geo_result = await geolocation_service.determine_work_mode(
        session, latitude, longitude, accuracy
    )

    log = AttendanceLog(
        emp_id=emp_id,
        timestamp=datetime.datetime.now(),
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
        ip_address=ip_address,
        work_mode=geo_result.work_mode,
        is_overridden=False,
    )

    saved_log = await attendance_repository.create_log(session, log)

    # Compute real-time tardiness status
    tardiness_status = await _check_tardiness(session, employee, saved_log)

    # If tardy, auto-generate summary so employee can submit a reason
    summary_id = None
    if tardiness_status in (AttendanceStatus.LATE, AttendanceStatus.EARLY_LEAVE):
        from app.services import reporting_service

        summary = await reporting_service.generate_daily_summary(
            session, emp_id, saved_log.timestamp.date()
        )
        if summary is not None:
            summary_id = summary.id

    return PunchResult(
        log=saved_log,
        work_mode=geo_result.work_mode,
        distance_km=geo_result.distance_km,
        is_low_accuracy=geo_result.is_low_accuracy,
        tardiness_status=tardiness_status,
        summary_id=summary_id,
    )


async def _check_tardiness(
    session: AsyncSession,
    employee: object,
    current_log: AttendanceLog,
) -> AttendanceStatus | None:
    """Check if the current punch indicates tardiness.

    Returns LATE if this is the first punch of the day and it's past the grace
    period. Returns EARLY_LEAVE if there's already a clock-in today and this
    punch is before shift end. Returns None otherwise.
    """
    today = current_log.timestamp.date()
    today_logs = await attendance_repository.find_by_employee_and_date(
        session, current_log.emp_id, today
    )

    grace_minutes = await system_config_repository.get_grace_period(session)

    if len(today_logs) <= 1:
        # First punch of the day — check for lateness
        grace_deadline = (
            datetime.datetime.combine(today, employee.shift_start_time)
            + datetime.timedelta(minutes=grace_minutes)
        ).time()
        if current_log.timestamp.time() > grace_deadline:
            return AttendanceStatus.LATE
    else:
        # Subsequent punch — check for early leave
        if current_log.timestamp.time() < employee.shift_end_time:
            return AttendanceStatus.EARLY_LEAVE

    return None


async def get_today_punches(
    session: AsyncSession,
    emp_id: str,
) -> list[AttendanceLog]:
    """Return all punch entries for *emp_id* on today's date (UTC)."""
    today = datetime.datetime.now().date()
    return await attendance_repository.find_by_employee_and_date(
        session, emp_id, today
    )


async def get_history(
    session: AsyncSession,
    emp_id: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[AttendanceLog]:
    """Return attendance logs for *emp_id* within the inclusive date range."""
    logs: list[AttendanceLog] = []
    current = start_date
    while current <= end_date:
        day_logs = await attendance_repository.find_by_employee_and_date(
            session, emp_id, current
        )
        logs.extend(day_logs)
        current += datetime.timedelta(days=1)
    return logs


async def get_team_logs(
    session: AsyncSession,
    manager_emp_id: str,
    start_date: datetime.date,
    end_date: datetime.date | None = None,
) -> list[AttendanceLog]:
    """Return attendance logs for the manager's department between *start_date* and *end_date* (inclusive).

    Raises
    ------
    ValueError
        If *manager_emp_id* does not correspond to an existing employee.
    """
    if end_date is None:
        end_date = start_date

    manager = await employee_repository.find_by_id(session, manager_emp_id)
    if manager is None:
        raise ValueError(f"Employee '{manager_emp_id}' not found")

    start = datetime.datetime.combine(start_date, datetime.time.min)
    end = datetime.datetime.combine(
        end_date + datetime.timedelta(days=1), datetime.time.min
    )
    return await attendance_repository.find_by_date_range_and_department(
        session, start, end, manager.department
    )


async def get_all_logs(
    session: AsyncSession,
    start_date: datetime.date,
    end_date: datetime.date | None = None,
) -> list[AttendanceLog]:
    """Return all attendance logs between *start_date* and *end_date* inclusive (HR/Admin use)."""
    if end_date is None:
        end_date = start_date

    start = datetime.datetime.combine(start_date, datetime.time.min)
    end = datetime.datetime.combine(
        end_date + datetime.timedelta(days=1), datetime.time.min
    )
    return await attendance_repository.find_by_date_range(session, start, end)


async def override_attendance(
    session: AsyncSession,
    manager_emp_id: str,
    target_emp_id: str,
    latitude: float,
    longitude: float,
    accuracy: float,
    ip_address: str,
    work_mode: WorkMode,
) -> AttendanceLog:
    """Create a manager-override attendance entry for *target_emp_id*.

    The override is recorded as a new immutable log with ``is_overridden=True``.

    Raises
    ------
    ValueError
        If *manager_emp_id* does not exist.
    PermissionError
        If the manager's role lacks the ``APPROVE_OVERRIDE`` permission.
    """
    manager = await employee_repository.find_by_id(session, manager_emp_id)
    if manager is None:
        raise ValueError(f"Employee '{manager_emp_id}' not found")

    if not has_permission(manager.role, APPROVE_OVERRIDE):
        raise PermissionError(
            f"Employee '{manager_emp_id}' is not authorized to override attendance"
        )

    log = AttendanceLog(
        emp_id=target_emp_id,
        timestamp=datetime.datetime.now(),
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
        ip_address=ip_address,
        work_mode=work_mode,
        is_overridden=True,
    )

    return await attendance_repository.create_log(session, log)
