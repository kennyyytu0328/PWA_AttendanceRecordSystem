"""Unit tests for the reporting-subtree resolver (Phase 15D)."""

import datetime

from app.models.employee import Employee, Role
from app.repositories import employee_repository as repo


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


async def _build_tree(db_session):
    # PRES
    #  ├ VP1 ─ AVP1 ─ MGR1 ─ EMP1
    #  │       └ AVP2
    #  └ VP2 ─ MGR2
    await _emp(db_session, "PRES", None, Role.MANAGER)
    await _emp(db_session, "VP1", "PRES", Role.MANAGER)
    await _emp(db_session, "VP2", "PRES", Role.MANAGER)
    await _emp(db_session, "AVP1", "VP1", Role.MANAGER)
    await _emp(db_session, "AVP2", "VP1", Role.MANAGER)
    await _emp(db_session, "MGR1", "AVP1", Role.MANAGER)
    await _emp(db_session, "MGR2", "VP2", Role.MANAGER)
    await _emp(db_session, "EMP1", "MGR1", Role.EMPLOYEE)


async def test_subtree_root_inclusive_full_tree(db_session):
    await _build_tree(db_session)
    assert await repo.get_subtree_emp_ids(db_session, "PRES") == {
        "PRES", "VP1", "VP2", "AVP1", "AVP2", "MGR1", "MGR2", "EMP1",
    }


async def test_subtree_mid_branch(db_session):
    await _build_tree(db_session)
    assert await repo.get_subtree_emp_ids(db_session, "VP1") == {
        "VP1", "AVP1", "AVP2", "MGR1", "EMP1",
    }
    assert await repo.get_subtree_emp_ids(db_session, "AVP1") == {
        "AVP1", "MGR1", "EMP1",
    }


async def test_subtree_leaf_is_self_only(db_session):
    await _build_tree(db_session)
    assert await repo.get_subtree_emp_ids(db_session, "EMP1") == {"EMP1"}


async def test_subtree_excludes_sibling_branch(db_session):
    await _build_tree(db_session)
    vp1 = await repo.get_subtree_emp_ids(db_session, "VP1")
    assert "VP2" not in vp1 and "MGR2" not in vp1


async def test_subtree_terminates_on_cycle(db_session):
    """A malformed A<->B cycle must not loop forever (UNION dedups)."""
    await _emp(db_session, "A", None, Role.MANAGER)
    await _emp(db_session, "B", "A", Role.MANAGER)
    # Force a cycle directly (bypassing the write guard).
    a = await repo.find_by_id(db_session, "A")
    a.reports_to = "B"
    await db_session.commit()

    result = await repo.get_subtree_emp_ids(db_session, "A")
    assert result == {"A", "B"}
