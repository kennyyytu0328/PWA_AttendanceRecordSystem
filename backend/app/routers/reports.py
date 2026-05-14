"""Reports router — daily reports, CSV/JSON export, summary generation."""

import datetime
import json

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_role
from app.models.employee import Role
from app.repositories import (
    employee_repository,
    monthly_submission_repository,
    reason_repository,
)
from app.services import reporting_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _normalize_submission_filter(value: str, role: str) -> str:
    """Validate the submission filter value.

    Unknown values silently coerce to 'submitted' (safest default).

    Note: this endpoint requires MANAGER+ role (enforced upstream), so all
    callers reaching this code legitimately need to see team punches.
    Managers need 'all' for daily team monitoring (the team page);
    HR/ADMIN need the full toggle on the reports page. UI gating decides
    which controls are exposed per role — the backend just validates.
    """
    allowed = {"submitted", "unsubmitted", "all"}
    return value if value in allowed else "submitted"


def _format_shift_time(emp) -> str:
    if emp is None:
        return ""
    return (
        f"{emp.shift_start_time.strftime('%H:%M')} - "
        f"{emp.shift_end_time.strftime('%H:%M')}"
    )


@router.get("/daily")
async def get_daily_report(
    start_date: datetime.date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: datetime.date = Query(..., description="End date (YYYY-MM-DD)"),
    department: str | None = Query(default=None, description="Filter by department"),
    emp_id: str | None = Query(default=None, description="Filter by employee ID"),
    status: str | None = Query(default=None, description="Filter by status"),
    include_terminated: bool = Query(
        default=False,
        description="Include resigned employees (HR/audit use — LSA retention).",
    ),
    submission_filter: str = Query(
        default="submitted",
        description=(
            "Submission visibility: 'submitted' (default), 'unsubmitted', "
            "or 'all'. Non-HR/ADMIN users are silently forced to 'submitted'."
        ),
    ),
    user: dict = require_role(Role.MANAGER),
    session: AsyncSession = Depends(get_db),
):
    """Get attendance report for a date range. Requires MANAGER+ role."""
    effective_filter = _normalize_submission_filter(
        submission_filter, user.get("role", "")
    )

    summaries = await reporting_service.get_daily_report(
        session,
        start_date=start_date,
        end_date=end_date,
        department=department,
        emp_id=emp_id,
        status_filter=status,
        include_terminated=include_terminated,
        submission_filter=effective_filter,
    )

    summary_ids = [s.id for s in summaries if s.id is not None]
    reasons = await reason_repository.find_by_summary_ids(session, summary_ids)
    reason_map = {r.summary_id: r.reason for r in reasons}

    # Build a map of emp_id -> Employee (for shift_time and other display fields).
    distinct_emp_ids = {s.emp_id for s in summaries}
    emp_map = {}
    for eid in distinct_emp_ids:
        emp = await employee_repository.find_by_id(session, eid)
        if emp is not None:
            emp_map[eid] = emp

    # Per-(year, month) submission cache.
    sub_cache: dict[tuple[int, int], set[str]] = {}

    async def _is_submitted(e: str, d: datetime.date) -> bool:
        key = (d.year, d.month)
        if key not in sub_cache:
            sub_cache[key] = await monthly_submission_repository.submitted_emp_ids(
                session, year=d.year, month=d.month
            )
        return e in sub_cache[key]

    rows = []
    for s in summaries:
        emp = emp_map.get(s.emp_id)
        submitted = await _is_submitted(s.emp_id, s.date)
        rows.append(
            {
                "id": s.id,
                "emp_id": s.emp_id,
                "name": emp.name if emp else "",
                "department": emp.department if emp else "",
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
                "reason": reason_map.get(s.id),
                "shift_time": _format_shift_time(emp),
                "submission_status": "submitted" if submitted else "unsubmitted",
            }
        )
    return rows


@router.get("/export")
async def export_report(
    format: str = Query(..., description="Export format: csv, json, or xlsx"),
    start_date: datetime.date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: datetime.date = Query(..., description="End date (YYYY-MM-DD)"),
    department: str | None = Query(default=None, description="Filter by department"),
    emp_id: str | None = Query(default=None, description="Filter by employee ID"),
    include_terminated: bool = Query(
        default=False,
        description="Include resigned employees (HR/audit use — LSA retention).",
    ),
    submission_filter: str = Query(
        default="submitted",
        description=(
            "Submission visibility: 'submitted' (default), 'unsubmitted', "
            "or 'all'. Non-HR/ADMIN users are silently forced to 'submitted'."
        ),
    ),
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
):
    """Export attendance data as CSV, JSON, or Excel. Requires HR+ role."""
    effective_filter = _normalize_submission_filter(
        submission_filter, user.get("role", "")
    )

    content = await reporting_service.export_attendance(
        session,
        start_date=start_date,
        end_date=end_date,
        format=format,
        department=department,
        emp_id=emp_id,
        include_terminated=include_terminated,
        submission_filter=effective_filter,
    )

    if format == "xlsx":
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=attendance_report_{start_date}_{end_date}.xlsx",
            },
        )

    if format == "csv":
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=attendance_report.csv",
            },
        )

    # JSON format — parse and return as JSON response
    return json.loads(content)


@router.post("/generate")
async def generate_daily_summaries(
    date: datetime.date = Query(..., description="Date to generate summaries for"),
    user: dict = require_role(Role.ADMIN),
    session: AsyncSession = Depends(get_db),
):
    """Generate or refresh daily attendance summaries. Requires ADMIN role."""
    summaries = await reporting_service.generate_all_summaries(session, date)

    return {
        "message": "Daily summaries generated successfully",
        "date": date.isoformat(),
        "generated_count": len(summaries),
    }
