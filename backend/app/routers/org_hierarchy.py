"""Org-hierarchy config routers (Phase 15C).

Two resources:
- /api/admin/ranks        — configurable ordered org-chart rank labels.
                            GET any authenticated user; PUT HR or above.
- /api/admin/org-scoping  — the system-wide subtree-scoped-authority switch.
                            GET any authenticated user; PUT ADMIN only, since
                            flipping it off would instantly restore company-wide
                            visibility to every manager.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_role
from app.models.employee import Role
from app.repositories import system_config_repository
from app.schemas.org_hierarchy import (
    OrgScopingResponse,
    OrgScopingUpdateRequest,
    RanksResponse,
    RanksUpdateRequest,
)

ranks_router = APIRouter(prefix="/api/admin/ranks", tags=["admin-ranks"])
scoping_router = APIRouter(
    prefix="/api/admin/org-scoping", tags=["admin-org-scoping"]
)


@ranks_router.get("", response_model=RanksResponse)
async def get_ranks(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RanksResponse:
    """Return the configured org-chart ranks. Any authenticated user."""
    ranks = await system_config_repository.get_ranks(session)
    return RanksResponse(ranks=ranks)


@ranks_router.put("", response_model=RanksResponse)
async def put_ranks(
    body: RanksUpdateRequest,
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> RanksResponse:
    """Replace the configured ranks list. Requires HR or above."""
    ranks = await system_config_repository.set_ranks(
        session, body.ranks, updated_by=user["sub"]
    )
    return RanksResponse(ranks=ranks)


@scoping_router.get("", response_model=OrgScopingResponse)
async def get_org_scoping(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrgScopingResponse:
    """Return whether subtree-scoped authority is active. Any authenticated user."""
    enabled = await system_config_repository.get_org_scoping_enabled(session)
    return OrgScopingResponse(enabled=enabled)


@scoping_router.put("", response_model=OrgScopingResponse)
async def put_org_scoping(
    body: OrgScopingUpdateRequest,
    user: dict = require_role(Role.ADMIN),
    session: AsyncSession = Depends(get_db),
) -> OrgScopingResponse:
    """Flip the subtree-scoped-authority switch. Requires ADMIN."""
    enabled = await system_config_repository.set_org_scoping_enabled(
        session, body.enabled, updated_by=user["sub"]
    )
    return OrgScopingResponse(enabled=enabled)
