"""Permission service — role-based access control via a permission matrix.

Each role maps to a frozenset of allowed actions. Higher roles inherit
all permissions from lower roles in the hierarchy:
ADMIN > HR > MANAGER > EMPLOYEE.
"""

from app.models.employee import Role

# ---------------------------------------------------------------------------
# Action constants
# ---------------------------------------------------------------------------
VIEW_OWN_ATTENDANCE: str = "view_own_attendance"
VIEW_TEAM_ATTENDANCE: str = "view_team_attendance"
VIEW_ALL_ATTENDANCE: str = "view_all_attendance"
CLOCK_IN_OUT: str = "clock_in_out"
MANAGE_EMPLOYEES: str = "manage_employees"
MANAGE_ROLES: str = "manage_roles"
CHANGE_OFFICE_LOCATION: str = "change_office_location"
MANAGE_CONFIG: str = "manage_config"
EXPORT_REPORTS: str = "export_reports"
APPROVE_OVERRIDE: str = "approve_override"

# ---------------------------------------------------------------------------
# Permission sets — built progressively so higher roles inherit lower ones
# ---------------------------------------------------------------------------
_EMPLOYEE_PERMISSIONS: frozenset[str] = frozenset({
    VIEW_OWN_ATTENDANCE,
    CLOCK_IN_OUT,
})

_MANAGER_PERMISSIONS: frozenset[str] = _EMPLOYEE_PERMISSIONS | frozenset({
    VIEW_TEAM_ATTENDANCE,
    APPROVE_OVERRIDE,
})

_HR_PERMISSIONS: frozenset[str] = _MANAGER_PERMISSIONS | frozenset({
    VIEW_ALL_ATTENDANCE,
    MANAGE_EMPLOYEES,
    CHANGE_OFFICE_LOCATION,
    EXPORT_REPORTS,
})

_ADMIN_PERMISSIONS: frozenset[str] = _HR_PERMISSIONS | frozenset({
    MANAGE_ROLES,
    MANAGE_CONFIG,
})

PERMISSION_MATRIX: dict[Role, frozenset[str]] = {
    Role.EMPLOYEE: _EMPLOYEE_PERMISSIONS,
    Role.MANAGER: _MANAGER_PERMISSIONS,
    Role.HR: _HR_PERMISSIONS,
    Role.ADMIN: _ADMIN_PERMISSIONS,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def has_permission(
    role: Role,
    action: str,
    resource: str | None = None,
    context: dict | None = None,
) -> bool:
    """Check whether *role* is allowed to perform *action*.

    Parameters
    ----------
    role:
        The employee's role.
    action:
        One of the action constants defined in this module.
    resource:
        Reserved for future context-aware checks (e.g. specific entity ID).
    context:
        Reserved for future context-aware checks (e.g. team membership).

    Returns
    -------
    bool
        ``True`` if the role's permission set includes *action*.
    """
    allowed_actions = PERMISSION_MATRIX.get(role, frozenset())
    return action in allowed_actions
