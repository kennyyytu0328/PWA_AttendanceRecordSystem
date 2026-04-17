"""Reports router — daily reports, CSV/JSON export, summary generation."""

import datetime
import json

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_role
from app.models.employee import Role
from app.repositories import reason_repository
from app.services import reporting_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


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
    user: dict = require_role(Role.MANAGER),
    session: AsyncSession = Depends(get_db),
):
    """Get attendance report for a date range. Requires MANAGER+ role."""
    summaries = await reporting_service.get_daily_report(
        session,
        start_date=start_date,
        end_date=end_date,
        department=department,
        emp_id=emp_id,
        status_filter=status,
        include_terminated=include_terminated,
    )

    summary_ids = [s.id for s in summaries if s.id is not None]
    reasons = await reason_repository.find_by_summary_ids(session, summary_ids)
    reason_map = {r.summary_id: r.reason for r in reasons}

    return [
        {
            "id": s.id,
            "emp_id": s.emp_id,
            "date": s.date.isoformat(),
            "first_clock_in": (
                s.first_clock_in.isoformat() if s.first_clock_in else None
            ),
            "last_clock_out": (
                s.last_clock_out.isoformat() if s.last_clock_out else None
            ),
            "status": s.status.value,
            "reason": reason_map.get(s.id),
        }
        for s in summaries
    ]


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
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
):
    """Export attendance data as CSV, JSON, or Excel. Requires HR+ role."""
    content = await reporting_service.export_attendance(
        session,
        start_date=start_date,
        end_date=end_date,
        format=format,
        department=department,
        emp_id=emp_id,
        include_terminated=include_terminated,
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
