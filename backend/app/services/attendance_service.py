"""Attendance service — punch workflow and override logic.

Orchestrates the clock-in/out flow: employee validation, geolocation-based
work-mode determination, immutable log creation, and manager overrides.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Role
from app.repositories import (
    attendance_repository,
    employee_repository,
    summary_repository,
    system_config_repository,
)
from app.services import geolocation_service, reporting_service
from app.services.permission_service import APPROVE_OVERRIDE, has_permission
from app.utils.taiwan_calendar import (
    DayInfo,
    DayKind,
    classify_indexed_date_kind,
    index_calendar,
    parse_calendar_json,
)


_HR_PLUS_ROLES = frozenset({Role.HR, Role.ADMIN})


async def _load_calendar_index(
    session: AsyncSession, year: int
) -> dict[datetime.date, DayInfo]:
    """Cached Taiwan calendar as a date→DayInfo dict for O(1) day_kind lookups."""
    cached = await system_config_repository.get_workday_calendar(session, year)
    data = parse_calendar_json(cached.get("entries", [])) if cached else []
    return index_calendar(data)

__all__ = [
    "PunchResult",
    "bulk_override_punches",
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

    # Reject live punches on rest day (Sat) / regular leave (Sun) — labor law
    # forbids regular Sunday work and Saturday overtime needs HR/ADMIN-supplied
    # 補登 instead of live punching. Makeup workdays (補班週六) bypass this.
    today = datetime.datetime.now().date()
    day_kind = classify_indexed_date_kind(
        await _load_calendar_index(session, today.year), today
    )
    if day_kind == DayKind.REGULAR_LEAVE:
        raise ValueError(
            "Sunday is 例假日 — live punching is not permitted (labor law)."
        )
    if day_kind == DayKind.REST_DAY:
        raise ValueError(
            "Saturday is 休息日 — please contact HR for 補登 instead of live punching."
        )

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
            session, emp_id, saved_log.timestamp.date(), day_kind=day_kind
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


async def get_logs_for_emp_ids(
    session: AsyncSession,
    emp_ids: set[str],
    start_date: datetime.date,
    end_date: datetime.date | None = None,
) -> list[AttendanceLog]:
    """Return logs for an explicit set of emp_ids (subtree-scoped team view)."""
    if end_date is None:
        end_date = start_date
    start = datetime.datetime.combine(start_date, datetime.time.min)
    end = datetime.datetime.combine(
        end_date + datetime.timedelta(days=1), datetime.time.min
    )
    return await attendance_repository.find_by_date_range_and_emp_ids(
        session, start, end, emp_ids
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


async def bulk_override_punches(
    session: AsyncSession,
    emp_id: str,
    requesting_user_id: str,
    requesting_user_role: Role,
    entries: list[dict],
) -> dict:
    """Bulk override attendance punches for an employee.

    Creates new log entries with is_overridden=True on old entries.
    Recalculates daily summaries for all affected dates.

    Raises
    ------
    ValueError
        If target employee not found.
    PermissionError
        If requesting user lacks permission.
    """
    is_hr_plus = requesting_user_role in _HR_PLUS_ROLES

    # Permission check — only the employee themselves or HR+ can override.
    if emp_id != requesting_user_id and not is_hr_plus:
        raise PermissionError(
            "You cannot override another employee's punches"
        )

    # Verify employee exists
    employee = await employee_repository.find_by_id(session, emp_id)
    if employee is None:
        raise ValueError(f"Employee {emp_id} not found")

    # Pre-load calendars for every year touched by the request as date→DayInfo
    # indexes so the Saturday (休息日 HR+ only) / Sunday (例假日 nobody) gate
    # is O(1) per entry instead of an O(n) linear scan.
    years_touched = {e["date"].year for e in entries}
    calendar_index: dict[int, dict[datetime.date, DayInfo]] = {
        y: await _load_calendar_index(session, y) for y in years_touched
    }

    results: list[dict] = []
    updated_count = 0

    for entry in entries:
        entry_date = entry["date"]
        clock_in_time = entry.get("first_clock_in")
        clock_out_time = entry.get("last_clock_out")
        leave_type = entry.get("leave_type")
        remark = entry.get("remark")
        overtime_hours = entry.get("overtime_hours")

        # Skip only when literally nothing changes
        if (
            clock_in_time is None
            and clock_out_time is None
            and leave_type is None
            and remark is None
            and overtime_hours is None
        ):
            continue

        # Labor-law / role gate per day.
        day_kind = classify_indexed_date_kind(
            calendar_index[entry_date.year], entry_date
        )
        if day_kind == DayKind.REGULAR_LEAVE:
            raise PermissionError(
                f"{entry_date} 為例假日（週日），依勞基法不得安排工作或補登"
            )
        if day_kind == DayKind.REST_DAY and not is_hr_plus:
            raise PermissionError(
                f"{entry_date} 為休息日（週六），僅 HR 或 ADMIN 可補登"
            )

        # Handle punches (existing behavior) — only touch logs when punches change.
        if clock_in_time is not None or clock_out_time is not None:
            # Mark existing logs as overridden
            await attendance_repository.mark_overridden_by_employee_and_date(
                session, emp_id, entry_date
            )

            # Create new clock-in log
            if clock_in_time is not None:
                clock_in_dt = datetime.datetime.combine(entry_date, clock_in_time)
                clock_in_log = AttendanceLog(
                    emp_id=emp_id,
                    timestamp=clock_in_dt,
                    latitude=0.0,
                    longitude=0.0,
                    accuracy=0.0,
                    ip_address="override",
                    work_mode=WorkMode.OFFICE,
                    is_overridden=False,
                )
                await attendance_repository.create_log(session, clock_in_log)

            # Create new clock-out log
            if clock_out_time is not None:
                clock_out_dt = datetime.datetime.combine(entry_date, clock_out_time)
                clock_out_log = AttendanceLog(
                    emp_id=emp_id,
                    timestamp=clock_out_dt,
                    latitude=0.0,
                    longitude=0.0,
                    accuracy=0.0,
                    ip_address="override",
                    work_mode=WorkMode.OFFICE,
                    is_overridden=False,
                )
                await attendance_repository.create_log(session, clock_out_log)

        # Stamp leave_type / remark / overtime_hours onto the existing summary
        # (or create a placeholder) so generate_daily_summary preserves them.
        if leave_type is not None or remark is not None or overtime_hours is not None:
            existing_summaries = await summary_repository.find_by_employee(
                session, emp_id, start_date=entry_date, end_date=entry_date
            )
            if existing_summaries:
                existing = existing_summaries[0]
                await summary_repository.upsert_summary(
                    session,
                    emp_id=emp_id,
                    date=entry_date,
                    first_clock_in=existing.first_clock_in,
                    last_clock_out=existing.last_clock_out,
                    status=existing.status,  # placeholder; regenerated next
                    leave_type=leave_type,
                    remark=remark,
                    overtime_hours=overtime_hours,
                )
            else:
                # No existing summary yet — create one with ABSENT placeholder;
                # generate_daily_summary will overwrite the status.
                await summary_repository.upsert_summary(
                    session,
                    emp_id=emp_id,
                    date=entry_date,
                    first_clock_in=None,
                    last_clock_out=None,
                    status=AttendanceStatus.ABSENT,
                    leave_type=leave_type,
                    remark=remark,
                    overtime_hours=overtime_hours,
                )

        # Recalculate summary (pass the calendar-accurate day_kind so weekend /
        # holiday overtime isn't mislabeled LATE/EARLY_LEAVE).
        summary = await reporting_service.generate_daily_summary(
            session, emp_id, entry_date, day_kind=day_kind
        )

        results.append({
            "date": str(entry_date),
            "first_clock_in": str(clock_in_time) if clock_in_time else None,
            "last_clock_out": str(clock_out_time) if clock_out_time else None,
            "status": summary.status.value if summary else None,
        })
        updated_count += 1

    await session.commit()

    return {
        "emp_id": emp_id,
        "updated_count": updated_count,
        "results": results,
    }
