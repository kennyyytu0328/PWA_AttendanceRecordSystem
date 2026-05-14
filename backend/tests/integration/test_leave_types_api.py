"""Integration tests for /api/admin/leave-types.

Task 14: GET allows any authenticated user; PUT requires HR or above.
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
    """Create a valid JWT token for testing."""
    role_value = role.value if isinstance(role, Role) else role
    payload = {
        "sub": emp_id,
        "role": role_value,
        "exp": datetime.datetime.now(UTC) + timedelta(hours=1),
    }
    return jose_jwt.encode(
        payload, settings.secret_key, algorithm=settings.algorithm
    )


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


async def test_get_leave_types_returns_seeded_defaults(
    client: AsyncClient, db_session: AsyncSession
):
    """Any authenticated user can read configured leave types."""
    # Test DB starts fresh via metadata.create_all (skips Alembic seed),
    # so seed via the repository helper directly to assert GET correctness.
    await system_config_repository.set_leave_types(
        db_session, ["特休", "公假", "病假"], updated_by="seed"
    )
    await _seed_employee(db_session, emp_id="EMP_READ")
    token = _make_token("EMP_READ", Role.EMPLOYEE)
    res = await client.get(
        "/api/admin/leave-types",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    types = res.json()["leave_types"]
    assert "特休" in types
    assert "公假" in types


async def test_put_leave_types_requires_hr(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="EMP_PUT")
    token = _make_token("EMP_PUT", Role.EMPLOYEE)
    res = await client.put(
        "/api/admin/leave-types",
        json={"leave_types": ["X", "Y"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


async def test_put_leave_types_as_hr_updates(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="HR_PUT", role=Role.HR)
    hr_token = _make_token("HR_PUT", Role.HR)
    res = await client.put(
        "/api/admin/leave-types",
        json={"leave_types": ["新假別A", "新假別B"]},
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["leave_types"] == ["新假別A", "新假別B"]
