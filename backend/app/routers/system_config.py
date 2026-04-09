"""System config router — office location and general config CRUD."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_role
from app.models.employee import Role
from app.repositories import system_config_repository
from app.schemas.system_config import SystemConfigResponse

router = APIRouter(prefix="/api/config", tags=["config"])


# ---------------------------------------------------------------------------
# Office location — accessible to any authenticated user (GET), HR+ (PUT)
# ---------------------------------------------------------------------------
@router.get("/office-location", response_model=SystemConfigResponse)
async def get_office_location(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SystemConfigResponse:
    """Return the current office location config."""
    config = await system_config_repository.get_by_key(session, "office_location")
    if config is None:
        return SystemConfigResponse(key="office_location", value=None)
    return SystemConfigResponse.model_validate(config)


@router.put("/office-location", response_model=SystemConfigResponse)
async def set_office_location(
    body: dict[str, Any],
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> SystemConfigResponse:
    """Set the office location. Requires HR role or above."""
    config = await system_config_repository.set_config(
        session,
        key="office_location",
        value=body,
        updated_by=user["sub"],
    )
    return SystemConfigResponse.model_validate(config)


# ---------------------------------------------------------------------------
# Departments — accessible to any authenticated user (GET), HR+ (PUT)
# ---------------------------------------------------------------------------
@router.get("/departments")
async def get_departments(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Return the list of pre-set departments."""
    departments = await system_config_repository.get_departments(session)
    return {"departments": departments}


@router.put("/departments")
async def set_departments(
    body: dict[str, Any],
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Set the list of departments. Requires HR role or above."""
    departments = body.get("departments")
    if departments is None or not isinstance(departments, list):
        raise HTTPException(status_code=422, detail="'departments' must be a list of strings")
    # Validate all items are non-empty strings
    cleaned = [str(d).strip() for d in departments if str(d).strip()]
    # Remove duplicates while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for d in cleaned:
        if d not in seen:
            seen.add(d)
            unique.append(d)

    await system_config_repository.set_config(
        session,
        key="departments",
        value={"list": unique},
        updated_by=user["sub"],
    )
    return {"departments": unique}


# ---------------------------------------------------------------------------
# Grace period — accessible to any authenticated user (GET), HR+ (PUT)
# ---------------------------------------------------------------------------
@router.get("/grace-period")
async def get_grace_period(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Return the current grace period in minutes."""
    config = await system_config_repository.get_by_key(session, "grace_period")
    if config is None:
        return {"minutes": 5}
    value = config.value
    if isinstance(value, dict) and "minutes" in value:
        return {"minutes": int(value["minutes"])}
    return {"minutes": 5}


@router.put("/grace-period")
async def set_grace_period(
    body: dict[str, Any],
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Set the grace period in minutes. Requires HR role or above."""
    minutes = body.get("minutes")
    if minutes is None or not isinstance(minutes, (int, float)):

        raise HTTPException(status_code=422, detail="'minutes' is required and must be a number")
    minutes = int(minutes)
    if minutes < 0 or minutes > 60:

        raise HTTPException(status_code=422, detail="Grace period must be between 0 and 60 minutes")

    await system_config_repository.set_config(
        session,
        key="grace_period",
        value={"minutes": minutes},
        updated_by=user["sub"],
    )
    return {"minutes": minutes}


# ---------------------------------------------------------------------------
# Generic config — ADMIN only
# ---------------------------------------------------------------------------
@router.get("/{key}", response_model=SystemConfigResponse)
async def get_config_by_key(
    key: str,
    user: dict = require_role(Role.ADMIN),
    session: AsyncSession = Depends(get_db),
) -> SystemConfigResponse:
    """Return a config entry by key. Requires ADMIN role."""
    config = await system_config_repository.get_by_key(session, key)
    if config is None:
        return SystemConfigResponse(key=key, value=None)
    return SystemConfigResponse.model_validate(config)


@router.put("/{key}", response_model=SystemConfigResponse)
async def set_config_by_key(
    key: str,
    body: dict[str, Any],
    user: dict = require_role(Role.ADMIN),
    session: AsyncSession = Depends(get_db),
) -> SystemConfigResponse:
    """Set a config entry by key. Requires ADMIN role."""
    value = body.get("value", body)
    config = await system_config_repository.set_config(
        session,
        key=key,
        value=value,
        updated_by=user["sub"],
    )
    return SystemConfigResponse.model_validate(config)
