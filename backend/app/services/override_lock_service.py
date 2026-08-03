"""Month-end override lock — blocks EMPLOYEE/MANAGER monthly edits while HR settles."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Role
from app.repositories import system_config_repository

_EXEMPT_ROLES = frozenset({Role.HR, Role.ADMIN})


async def ensure_not_locked(session: AsyncSession, role: Role) -> None:
    """Raise PermissionError when the lock is on and *role* is not exempt."""
    if role in _EXEMPT_ROLES:
        return
    if await system_config_repository.get_monthly_override_locked(session):
        raise PermissionError("月結鎖定中，月度打卡修改與送單暫停開放，請聯絡人資")
