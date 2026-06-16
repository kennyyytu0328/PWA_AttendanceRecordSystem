"""Integration tests for Phase 15C org-hierarchy config endpoints.

- GET  /api/admin/ranks         — any authenticated user
- PUT  /api/admin/ranks         — HR or above
- GET  /api/admin/org-scoping   — any authenticated user
- PUT  /api/admin/org-scoping   — ADMIN only (system-wide authority switch)
"""

import datetime
from datetime import UTC, timedelta

from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
from app.repositories import system_config_repository
from app.utils.password import hash_password


def _make_token(emp_id: str, role: Role | str) -> str:
    role_value = role.value if isinstance(role, Role) else role
    payload = {
        "sub": emp_id,
        "role": role_value,
        "exp": datetime.datetime.now(UTC) + timedelta(hours=1),
    }
    return jose_jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


async def _seed_employee(
    db_session: AsyncSession,
    emp_id: str,
    role: Role | str = Role.EMPLOYEE,
) -> Employee:
    role_enum = role if isinstance(role, Role) else Role(role)
    emp = Employee(
        emp_id=emp_id,
        name=f"User {emp_id}",
        department="Engineering",
        role=role_enum,
        hashed_password=hash_password("pass1234"),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


# --------------------------------------------------------------------------
# Ranks
# --------------------------------------------------------------------------
async def test_get_ranks_returns_defaults_for_any_user(
    client: AsyncClient, db_session: AsyncSession
):
    """Unconfigured ranks fall back to the default 4-tier ladder."""
    await _seed_employee(db_session, emp_id="EMP_R")
    token = _make_token("EMP_R", Role.EMPLOYEE)
    res = await client.get(
        "/api/admin/ranks", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["ranks"] == ["PRESIDENT", "VP", "AVP", "MANAGER"]


async def test_put_ranks_requires_hr(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="EMP_R2")
    token = _make_token("EMP_R2", Role.EMPLOYEE)
    res = await client.put(
        "/api/admin/ranks",
        json={"ranks": ["PRESIDENT", "MANAGER"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


async def test_put_ranks_as_hr_updates(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="HR_R", role=Role.HR)
    token = _make_token("HR_R", Role.HR)
    res = await client.put(
        "/api/admin/ranks",
        json={"ranks": ["PRESIDENT", "SVP", "VP", "AVP", "MANAGER", "LEAD"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["ranks"] == [
        "PRESIDENT",
        "SVP",
        "VP",
        "AVP",
        "MANAGER",
        "LEAD",
    ]


# --------------------------------------------------------------------------
# Org-scoping toggle
# --------------------------------------------------------------------------
async def test_get_org_scoping_defaults_off(
    client: AsyncClient, db_session: AsyncSession
):
    """Default OFF so an empty tree never hides managers' team views."""
    await _seed_employee(db_session, emp_id="EMP_S")
    token = _make_token("EMP_S", Role.EMPLOYEE)
    res = await client.get(
        "/api/admin/org-scoping", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is False


async def test_put_org_scoping_requires_hr(
    client: AsyncClient, db_session: AsyncSession
):
    """Below HR cannot flip the authority switch."""
    await _seed_employee(db_session, emp_id="MGR_S", role=Role.MANAGER)
    token = _make_token("MGR_S", Role.MANAGER)
    res = await client.put(
        "/api/admin/org-scoping",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


async def test_put_org_scoping_as_hr_enables(
    client: AsyncClient, db_session: AsyncSession
):
    """HR runs the rollout, so HR may flip the switch (HR+ allowed)."""
    await _seed_employee(db_session, emp_id="HR_S", role=Role.HR)
    token = _make_token("HR_S", Role.HR)
    res = await client.put(
        "/api/admin/org-scoping",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is True

    # Round-trips on the next read.
    res2 = await client.get(
        "/api/admin/org-scoping", headers={"Authorization": f"Bearer {token}"}
    )
    assert res2.json()["enabled"] is True


async def test_put_org_scoping_as_admin_enables(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="ADMIN_S", role=Role.ADMIN)
    token = _make_token("ADMIN_S", Role.ADMIN)
    res = await client.put(
        "/api/admin/org-scoping",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is True
