"""Tests for GET /api/auth/me returning name + shift times.

The JWT payload only carries emp_id + role; the punch page's late-leave
dialog (and the monthly-override required-reason rule) need the logged-in
user's own shift_end_time, so /me looks up the employee row and adds
name/shift_start_time/shift_end_time (omitted only if the row is missing).
"""

import datetime
from datetime import UTC, timedelta

import pytest
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


@pytest.mark.asyncio
async def test_me_includes_shift_times(client, db_session):
    await _seed_employee(db_session, "E970")  # shift 09:00-18:00
    token = _make_token("E970", "EMPLOYEE")
    res = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["emp_id"] == "E970"
    assert body["shift_start_time"] == "09:00"
    assert body["shift_end_time"] == "18:00"
    assert body["name"] == "User E970"
