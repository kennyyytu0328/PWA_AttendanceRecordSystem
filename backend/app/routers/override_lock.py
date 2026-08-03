"""Override-lock config router.

GET — any authenticated user (pages need it to render read-only state).
PUT — HR or above; flips the month-end settlement lock.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_role
from app.models.employee import Role
from app.repositories import system_config_repository
from app.schemas.override_lock import OverrideLockResponse, OverrideLockUpdateRequest

router = APIRouter(prefix="/api/admin/override-lock", tags=["admin-override-lock"])


@router.get("", response_model=OverrideLockResponse)
async def get_override_lock(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OverrideLockResponse:
    locked = await system_config_repository.get_monthly_override_locked(session)
    return OverrideLockResponse(locked=locked)


@router.put("", response_model=OverrideLockResponse)
async def put_override_lock(
    body: OverrideLockUpdateRequest,
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> OverrideLockResponse:
    locked = await system_config_repository.set_monthly_override_locked(
        session, body.locked, updated_by=user["sub"]
    )
    return OverrideLockResponse(locked=locked)
