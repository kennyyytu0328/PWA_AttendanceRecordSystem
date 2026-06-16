"""Attendance router — punch, history, team/all views, and manager overrides."""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_role
from app.middleware.scope import resolve_scope
from app.models.employee import Role
from app.schemas.attendance import (
    AttendanceLogResponse,
    OverrideRequest,
    PunchGPSRequest,
    PunchResponse,
)
from app.schemas.bulk_override import BulkOverrideRequest
from app.services import attendance_service

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


@router.post("/punch", response_model=PunchResponse)
async def punch(
    body: PunchGPSRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Record a clock-in/out punch for the authenticated employee."""
    ip_address = request.client.host if request.client else "unknown"

    try:
        result = await attendance_service.punch(
            session,
            emp_id=user["sub"],
            latitude=body.latitude,
            longitude=body.longitude,
            accuracy=body.accuracy,
            ip_address=ip_address,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return PunchResponse(
        work_mode=result.work_mode,
        distance_km=result.distance_km,
        is_low_accuracy=result.is_low_accuracy,
        log=AttendanceLogResponse.model_validate(result.log),
        tardiness_status=result.tardiness_status.value if result.tardiness_status else None,
        summary_id=result.summary_id,
    )


@router.get("/today", response_model=list[AttendanceLogResponse])
async def get_today(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Return today's attendance logs for the authenticated employee."""
    logs = await attendance_service.get_today_punches(session, user["sub"])
    return [AttendanceLogResponse.model_validate(log) for log in logs]


@router.get("/team", response_model=list[AttendanceLogResponse])
async def get_team(
    start_date: datetime.date = Query(...),
    end_date: datetime.date = Query(...),
    user: dict = require_role(Role.MANAGER),
    session: AsyncSession = Depends(get_db),
):
    """Return attendance logs for the manager's team between start_date and end_date (inclusive).

    When subtree scoping is active the team is the manager's reporting subtree;
    otherwise (toggle off, or HR/ADMIN) the legacy department-scoped view stands.
    """
    scope = await resolve_scope(user, session)
    try:
        if scope.company_wide:
            logs = await attendance_service.get_team_logs(
                session, user["sub"], start_date, end_date
            )
        else:
            logs = await attendance_service.get_logs_for_emp_ids(
                session, set(scope.visible_emp_ids or set()), start_date, end_date
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return [AttendanceLogResponse.model_validate(log) for log in logs]


@router.get("/all", response_model=list[AttendanceLogResponse])
async def get_all(
    start_date: datetime.date = Query(...),
    end_date: datetime.date = Query(...),
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
):
    """Return all attendance logs between start_date and end_date inclusive (HR/Admin only)."""
    logs = await attendance_service.get_all_logs(session, start_date, end_date)
    return [AttendanceLogResponse.model_validate(log) for log in logs]


@router.get("", response_model=list[AttendanceLogResponse])
async def get_history(
    start_date: datetime.date = Query(...),
    end_date: datetime.date = Query(...),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Return attendance history for the authenticated employee."""
    logs = await attendance_service.get_history(
        session, user["sub"], start_date, end_date
    )
    return [AttendanceLogResponse.model_validate(log) for log in logs]


@router.get("/summaries")
async def get_my_summaries(
    start_date: datetime.date = Query(...),
    end_date: datetime.date = Query(...),
    emp_id: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Return daily attendance summaries.

    Employees see only their own summaries. HR+ may pass ``emp_id`` to
    view another employee's data (used by the monthly override page).
    """
    from app.services import permission_service, reporting_service

    target_emp_id = user["sub"]
    if emp_id and emp_id != user["sub"]:
        if not permission_service.has_permission(
            Role(user["role"]), permission_service.VIEW_ALL_ATTENDANCE
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view other employees' summaries",
            )
        target_emp_id = emp_id

    summaries = await reporting_service.get_daily_report(
        session,
        start_date=start_date,
        end_date=end_date,
        emp_id=target_emp_id,
        # Editing surface — never hide unsubmitted rows. The whole point of
        # the monthly-override page is to prepare data *before* submission.
        submission_filter="all",
    )
    return [
        {
            "date": s.date.isoformat(),
            "first_clock_in": (
                s.first_clock_in.isoformat() if s.first_clock_in else None
            ),
            "last_clock_out": (
                s.last_clock_out.isoformat() if s.last_clock_out else None
            ),
            "status": s.status.value,
            "leave_type": s.leave_type,
            "remark": s.remark,
            "overtime_hours": (
                float(s.overtime_hours) if s.overtime_hours is not None else None
            ),
        }
        for s in summaries
    ]


@router.post("/override", response_model=AttendanceLogResponse)
async def override(
    body: OverrideRequest,
    request: Request,
    user: dict = require_role(Role.MANAGER),
    session: AsyncSession = Depends(get_db),
):
    """Create a manager-override attendance entry.

    When subtree scoping is active a manager may only override employees in
    their own reporting subtree; HR/ADMIN (and the toggle-off path) are
    unrestricted, preserving the prior behavior.
    """
    scope = await resolve_scope(user, session)
    if not scope.can_see(body.target_emp_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to override an employee outside your team",
        )

    ip_address = request.client.host if request.client else "unknown"

    try:
        log = await attendance_service.override_attendance(
            session,
            manager_emp_id=user["sub"],
            target_emp_id=body.target_emp_id,
            latitude=body.latitude,
            longitude=body.longitude,
            accuracy=body.accuracy,
            ip_address=ip_address,
            work_mode=body.work_mode,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )

    return AttendanceLogResponse.model_validate(log)


@router.put("/override-bulk")
async def bulk_override(
    body: BulkOverrideRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Bulk override attendance punches for a month."""
    target_emp_id = body.emp_id if body.emp_id else user["sub"]
    try:
        result = await attendance_service.bulk_override_punches(
            session,
            emp_id=target_emp_id,
            requesting_user_id=user["sub"],
            requesting_user_role=Role(user["role"]),
            entries=[
                {
                    "date": entry.date,
                    "first_clock_in": entry.first_clock_in,
                    "last_clock_out": entry.last_clock_out,
                    "leave_type": entry.leave_type,
                    "remark": entry.remark,
                    "overtime_hours": entry.overtime_hours,
                }
                for entry in body.entries
            ],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result
