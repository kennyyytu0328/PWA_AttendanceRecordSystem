"""Unit tests for resolve_scope (Phase 15D authority engine)."""

import datetime

from app.middleware.scope import resolve_scope
from app.models.employee import Employee, Role
from app.repositories import system_config_repository


async def _emp(db_session, emp_id, reports_to=None, role=Role.EMPLOYEE):
    e = Employee(
        emp_id=emp_id,
        name=emp_id,
        department="Sales",
        role=role,
        reports_to=reports_to,
        hashed_password="hpw",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(e)
    await db_session.commit()
    return e


def _user(emp_id, role):
    return {"sub": emp_id, "role": role.value}


async def test_hr_admin_company_wide_regardless_of_toggle(db_session):
    await _emp(db_session, "HR1", role=Role.HR)
    await system_config_repository.set_org_scoping_enabled(db_session, True)
    scope = await resolve_scope(_user("HR1", Role.HR), db_session)
    assert scope.company_wide is True
    assert scope.can_see("ANYONE") is True


async def test_manager_scoped_to_subtree_when_enabled(db_session):
    await _emp(db_session, "MGR1", role=Role.MANAGER)
    await _emp(db_session, "EMP1", reports_to="MGR1", role=Role.EMPLOYEE)
    await _emp(db_session, "OTHER", role=Role.EMPLOYEE)
    await system_config_repository.set_org_scoping_enabled(db_session, True)

    scope = await resolve_scope(_user("MGR1", Role.MANAGER), db_session)
    assert scope.company_wide is False
    assert scope.can_see("MGR1") is True   # root inclusive
    assert scope.can_see("EMP1") is True   # direct report
    assert scope.can_see("OTHER") is False  # not in subtree


async def test_manager_company_wide_when_toggle_off(db_session):
    """Toggle OFF preserves the pre-feature behavior: manager sees everyone."""
    await _emp(db_session, "MGR1", role=Role.MANAGER)
    await _emp(db_session, "OTHER", role=Role.EMPLOYEE)
    # default off (no config set)
    scope = await resolve_scope(_user("MGR1", Role.MANAGER), db_session)
    assert scope.company_wide is True
    assert scope.can_see("OTHER") is True


async def test_employee_self_only_when_enabled(db_session):
    await _emp(db_session, "EMP1", role=Role.EMPLOYEE)
    await _emp(db_session, "EMP2", role=Role.EMPLOYEE)
    await system_config_repository.set_org_scoping_enabled(db_session, True)
    scope = await resolve_scope(_user("EMP1", Role.EMPLOYEE), db_session)
    assert scope.company_wide is False
    assert scope.can_see("EMP1") is True
    assert scope.can_see("EMP2") is False
