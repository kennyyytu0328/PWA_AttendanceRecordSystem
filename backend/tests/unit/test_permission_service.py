"""Unit tests for the permission service."""

from app.models.employee import Role
from app.services.permission_service import (
    APPROVE_OVERRIDE,
    CHANGE_OFFICE_LOCATION,
    CLOCK_IN_OUT,
    EXPORT_REPORTS,
    MANAGE_CONFIG,
    MANAGE_EMPLOYEES,
    MANAGE_ROLES,
    VIEW_ALL_ATTENDANCE,
    VIEW_OWN_ATTENDANCE,
    VIEW_TEAM_ATTENDANCE,
    has_permission,
)


class TestEmployeePermissions:
    """Tests for the EMPLOYEE role permissions."""

    def test_employee_can_view_own_attendance(self) -> None:
        assert has_permission(Role.EMPLOYEE, VIEW_OWN_ATTENDANCE) is True

    def test_employee_cannot_view_others_attendance(self) -> None:
        assert has_permission(Role.EMPLOYEE, VIEW_TEAM_ATTENDANCE) is False

    def test_employee_cannot_manage_employees(self) -> None:
        assert has_permission(Role.EMPLOYEE, MANAGE_EMPLOYEES) is False

    def test_employee_cannot_change_system_config(self) -> None:
        assert has_permission(Role.EMPLOYEE, MANAGE_CONFIG) is False


class TestManagerPermissions:
    """Tests for the MANAGER role permissions."""

    def test_manager_can_view_team_attendance(self) -> None:
        assert has_permission(Role.MANAGER, VIEW_TEAM_ATTENDANCE) is True

    def test_manager_cannot_view_other_team(self) -> None:
        assert has_permission(Role.MANAGER, VIEW_ALL_ATTENDANCE) is False

    def test_manager_cannot_change_office_location(self) -> None:
        assert has_permission(Role.MANAGER, CHANGE_OFFICE_LOCATION) is False


class TestHRPermissions:
    """Tests for the HR role permissions."""

    def test_hr_can_view_all_attendance(self) -> None:
        assert has_permission(Role.HR, VIEW_ALL_ATTENDANCE) is True

    def test_hr_can_manage_employees(self) -> None:
        assert has_permission(Role.HR, MANAGE_EMPLOYEES) is True

    def test_hr_can_change_office_location(self) -> None:
        assert has_permission(Role.HR, CHANGE_OFFICE_LOCATION) is True

    def test_hr_can_export_reports(self) -> None:
        assert has_permission(Role.HR, EXPORT_REPORTS) is True


class TestAdminPermissions:
    """Tests for the ADMIN role permissions."""

    def test_admin_has_full_access(self) -> None:
        all_actions = [
            VIEW_OWN_ATTENDANCE,
            VIEW_TEAM_ATTENDANCE,
            VIEW_ALL_ATTENDANCE,
            CLOCK_IN_OUT,
            MANAGE_EMPLOYEES,
            MANAGE_ROLES,
            CHANGE_OFFICE_LOCATION,
            MANAGE_CONFIG,
            EXPORT_REPORTS,
            APPROVE_OVERRIDE,
        ]
        for action in all_actions:
            assert has_permission(Role.ADMIN, action) is True, (
                f"ADMIN should have permission for {action}"
            )


class TestRoleHierarchy:
    """Tests that higher roles inherit all permissions of lower roles."""

    def test_role_hierarchy_respected(self) -> None:
        employee_actions = [VIEW_OWN_ATTENDANCE, CLOCK_IN_OUT]
        manager_actions = [*employee_actions, VIEW_TEAM_ATTENDANCE, APPROVE_OVERRIDE]
        hr_actions = [
            *manager_actions,
            VIEW_ALL_ATTENDANCE,
            MANAGE_EMPLOYEES,
            CHANGE_OFFICE_LOCATION,
            EXPORT_REPORTS,
        ]
        admin_actions = [*hr_actions, MANAGE_ROLES, MANAGE_CONFIG]

        # MANAGER has all EMPLOYEE permissions
        for action in employee_actions:
            assert has_permission(Role.MANAGER, action) is True, (
                f"MANAGER should inherit EMPLOYEE permission: {action}"
            )

        # HR has all MANAGER permissions
        for action in manager_actions:
            assert has_permission(Role.HR, action) is True, (
                f"HR should inherit MANAGER permission: {action}"
            )

        # ADMIN has all HR permissions
        for action in hr_actions:
            assert has_permission(Role.ADMIN, action) is True, (
                f"ADMIN should inherit HR permission: {action}"
            )

        # Verify full ADMIN coverage
        for action in admin_actions:
            assert has_permission(Role.ADMIN, action) is True, (
                f"ADMIN should have permission: {action}"
            )


def test_hr_cannot_delete_employee():
    assert has_permission(Role.HR, "delete_employee") is False


def test_admin_can_delete_employee():
    assert has_permission(Role.ADMIN, "delete_employee") is True


def test_manager_cannot_delete_employee():
    assert has_permission(Role.MANAGER, "delete_employee") is False
