"""Reasons router — submit and view late/early-leave reasons."""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_role
from app.models.employee import Role
from app.schemas.attendance_reason import ReasonResponse, ReasonSubmitRequest
from app.services import reason_service

router = APIRouter(prefix="/api/reasons", tags=["reasons"])


@router.post("", response_model=ReasonResponse, status_code=status.HTTP_201_CREATED)
async def submit_reason(
    body: ReasonSubmitRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Submit a reason for a LATE or EARLY_LEAVE daily summary."""
    try:
        reason = await reason_service.submit_reason(
            session,
            emp_id=user["sub"],
            summary_id=body.summary_id,
            reason_text=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return ReasonResponse.model_validate(reason)


@router.get("/me", response_model=list[ReasonResponse])
async def get_my_reasons(
    start_date: datetime.date | None = Query(default=None),
    end_date: datetime.date | None = Query(default=None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Return the authenticated employee's submitted reasons."""
    reasons = await reason_service.get_reasons_for_employee(
        session, user["sub"], start_date, end_date
    )
    return [ReasonResponse.model_validate(r) for r in reasons]


@router.get("", response_model=list[ReasonResponse])
async def get_reasons_by_employee(
    emp_id: str = Query(..., description="Employee ID to query"),
    start_date: datetime.date | None = Query(default=None),
    end_date: datetime.date | None = Query(default=None),
    user: dict = require_role(Role.MANAGER),
    session: AsyncSession = Depends(get_db),
):
    """Return reasons for a specific employee. Requires MANAGER+ role."""
    reasons = await reason_service.get_reasons_for_employee(
        session, emp_id, start_date, end_date
    )
    return [ReasonResponse.model_validate(r) for r in reasons]
