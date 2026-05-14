"""Monthly submission router — POST submits a month, GET reports status.

Permission rules:
- An employee may submit / query their own month.
- HR and ADMIN may submit / query any employee's month.
- All other cross-employee requests get 403.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.employee import Role
from app.schemas.monthly_submission import (
    SubmissionResponse,
    SubmissionStatusResponse,
    SubmitMonthRequest,
)
from app.services import monthly_submission_service

router = APIRouter(prefix="/api/monthly-submissions", tags=["monthly-submissions"])


def _can_act_on(user: dict, target_emp_id: str) -> bool:
    """True if the caller may submit/query on behalf of *target_emp_id*."""
    if user.get("sub") == target_emp_id:
        return True
    try:
        role = Role(user.get("role"))
    except ValueError:
        return False
    return role in (Role.HR, Role.ADMIN)


@router.post("", response_model=SubmissionResponse)
async def submit_month(
    body: SubmitMonthRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SubmissionResponse:
    if not _can_act_on(user, body.emp_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot submit for another employee",
        )

    row = await monthly_submission_service.submit_month(
        session, emp_id=body.emp_id, year=body.year, month=body.month
    )
    return SubmissionResponse(
        emp_id=row.emp_id,
        year=row.year,
        month=row.month,
        submitted_at=row.submitted_at,
    )


@router.get("", response_model=SubmissionStatusResponse)
async def get_status(
    emp_id: str,
    year: int,
    month: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SubmissionStatusResponse:
    if not _can_act_on(user, emp_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view another employee's submission status",
        )

    row = await monthly_submission_service.get_status(
        session, emp_id=emp_id, year=year, month=month
    )
    if row is None:
        return SubmissionStatusResponse(submitted=False)
    return SubmissionStatusResponse(submitted=True, submitted_at=row.submitted_at)
