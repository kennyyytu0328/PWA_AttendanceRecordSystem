"""Leave-types config router.

GET — any authenticated user may read the configured leave types.
PUT — requires HR or above; replaces the full list.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_role
from app.models.employee import Role
from app.repositories import system_config_repository
from app.schemas.leave_types import LeaveTypesResponse, LeaveTypesUpdateRequest

router = APIRouter(prefix="/api/admin/leave-types", tags=["admin-leave-types"])


@router.get("", response_model=LeaveTypesResponse)
async def get_leave_types(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> LeaveTypesResponse:
    """Return the configured leave types. Any authenticated user."""
    types = await system_config_repository.get_leave_types(session)
    return LeaveTypesResponse(leave_types=types)


@router.put("", response_model=LeaveTypesResponse)
async def put_leave_types(
    body: LeaveTypesUpdateRequest,
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> LeaveTypesResponse:
    """Replace the configured leave types. Requires HR or above."""
    types = await system_config_repository.set_leave_types(
        session, body.leave_types, updated_by=user["sub"]
    )
    return LeaveTypesResponse(leave_types=types)
