"""Integration tests for /api/monthly-submissions.

Task 13: POST submits a month (employees for self, HR/ADMIN for anyone),
GET reports whether a month has been submitted.
"""

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


async def test_employee_submits_own_month(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="E050")
    token = _make_token("E050", Role.EMPLOYEE)
    res = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E050", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["emp_id"] == "E050"
    assert body["year"] == 2026
    assert body["month"] == 5
    assert body["submitted_at"] is not None


async def test_employee_cannot_submit_other_employee(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="E051")
    await _seed_employee(db_session, emp_id="E999")
    token = _make_token("E051", Role.EMPLOYEE)
    res = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E999", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


async def test_hr_can_submit_any_employee(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="HR_USER", role=Role.HR)
    await _seed_employee(db_session, emp_id="E060")
    hr_token = _make_token("HR_USER", Role.HR)
    res = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E060", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert res.status_code == 200, res.text


async def test_resubmit_updates_timestamp(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="E070")
    token = _make_token("E070", Role.EMPLOYEE)
    r1 = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E070", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    r2 = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E070", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["submitted_at"] >= r1.json()["submitted_at"]


async def test_get_status_reflects_submission(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="E080")
    token = _make_token("E080", Role.EMPLOYEE)
    before = await client.get(
        "/api/monthly-submissions?emp_id=E080&year=2026&month=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert before.status_code == 200
    assert before.json()["submitted"] is False

    await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E080", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    after = await client.get(
        "/api/monthly-submissions?emp_id=E080&year=2026&month=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after.status_code == 200
    assert after.json()["submitted"] is True
    assert after.json()["submitted_at"] is not None
