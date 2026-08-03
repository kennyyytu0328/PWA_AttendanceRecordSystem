"""Month-end override lock — HR/ADMIN exempt, EMPLOYEE/MANAGER blocked."""

import datetime
from datetime import UTC, timedelta

import pytest
from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
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


ENTRY = {"date": "2026-05-14", "first_clock_in": "09:00", "last_clock_out": "18:00"}


async def _set_lock(client, locked: bool):
    hr_token = _make_token("HRX", "HR")
    res = await client.put("/api/admin/override-lock", json={"locked": locked},
                           headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 200, res.text
    return res


@pytest.mark.asyncio
async def test_lock_blocks_employee_but_not_hr(client, db_session):
    await _seed_employee(db_session, "E940")
    await _seed_employee(db_session, "HRX", role=Role.HR)
    await _set_lock(client, True)

    # Employee blocked from bulk override
    emp_token = _make_token("E940", "EMPLOYEE")
    res = await client.put("/api/attendance/override-bulk",
        json={"year": 2026, "month": 5, "entries": [ENTRY]},
        headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 403

    # Employee blocked from submission
    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E940", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 403

    # HR can still bulk-override the employee
    hr_token = _make_token("HRX", "HR")
    res = await client.put("/api/attendance/override-bulk",
        json={"year": 2026, "month": 5, "emp_id": "E940", "entries": [ENTRY]},
        headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 200, res.text

    # Release restores employee access
    await _set_lock(client, False)
    res = await client.put("/api/attendance/override-bulk",
        json={"year": 2026, "month": 5, "entries": [ENTRY]},
        headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_lock_read_any_auth_write_hr_only(client, db_session):
    await _seed_employee(db_session, "E941")
    emp_token = _make_token("E941", "EMPLOYEE")
    res = await client.get("/api/admin/override-lock",
                           headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 200
    assert res.json() == {"locked": False}

    res = await client.put("/api/admin/override-lock", json={"locked": True},
                           headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 403
