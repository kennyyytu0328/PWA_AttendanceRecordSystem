"""Authority scope resolution (Phase 15D).

Computes *which employees* a caller may act on, as opposed to *what actions*
they may perform (that is the permission_service's job). Authority follows the
reporting tree (``reports_to``), not the department label:

- HR / ADMIN  -> company-wide (see everyone).
- MANAGER     -> their own reporting subtree (root inclusive).
- EMPLOYEE    -> only themselves.

Gated by the ``org_scoping_enabled`` system flag. While it is OFF (the default),
everyone resolves to company-wide so the pre-feature behavior is preserved and
an empty reporting tree never hides a manager's team. ADMIN/HR flips it ON once
the tree is populated.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Role
from app.repositories import employee_repository, system_config_repository


@dataclass(frozen=True)
class Scope:
    """The set of employees a caller may act on."""

    role: Role
    emp_id: str
    company_wide: bool
    # None when company_wide; otherwise the explicit set of visible emp_ids.
    visible_emp_ids: frozenset[str] | None

    def can_see(self, target_emp_id: str) -> bool:
        """Whether the caller may act on *target_emp_id*."""
        if self.company_wide:
            return True
        return target_emp_id in (self.visible_emp_ids or frozenset())


async def resolve_scope(user: dict, session: AsyncSession) -> Scope:
    """Resolve the caller's authority scope from their role + the reporting tree."""
    role = Role(user["role"])
    emp_id = user["sub"]

    # Functional roles always see everyone.
    if role in (Role.HR, Role.ADMIN):
        return Scope(role, emp_id, company_wide=True, visible_emp_ids=None)

    # Feature switch off -> preserve pre-feature company-wide behavior.
    if not await system_config_repository.get_org_scoping_enabled(session):
        return Scope(role, emp_id, company_wide=True, visible_emp_ids=None)

    if role == Role.MANAGER:
        ids = await employee_repository.get_subtree_emp_ids(session, emp_id)
        return Scope(
            role, emp_id, company_wide=False, visible_emp_ids=frozenset(ids)
        )

    # EMPLOYEE — only themselves.
    return Scope(
        role, emp_id, company_wide=False, visible_emp_ids=frozenset({emp_id})
    )
