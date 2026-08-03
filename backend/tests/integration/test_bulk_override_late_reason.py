"""Tests for late_leave_reason round-trip via bulk override.

Same key-presence semantics as leave_type/remark/overtime_hours (#38):
an explicit JSON ``null`` clears the stored value; omitting the key
leaves it alone.
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


async def _get_summary_row(
    client: AsyncClient, token: str, date: str
) -> dict:
    res = await client.get(
        f"/api/attendance/summaries?start_date={date}&end_date={date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    return next(r for r in res.json() if r["date"] == date)


@pytest.mark.asyncio
async def test_bulk_override_sets_and_clears_late_reason(client, db_session):
    await _seed_employee(db_session, emp_id="E920")
    token = _make_token("E920", "EMPLOYEE")
    headers = {"Authorization": f"Bearer {token}"}

    # Set punches + reason (2026-05-14 is a Thursday workday)
    res = await client.put("/api/attendance/override-bulk", json={
        "year": 2026, "month": 5,
        "entries": [{"date": "2026-05-14", "first_clock_in": "09:00",
                     "last_clock_out": "19:00",
                     "late_leave_reason": "ASSIGNED_OVERTIME"}],
    }, headers=headers)
    assert res.status_code == 200, res.text
    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["late_leave_reason"] == "ASSIGNED_OVERTIME"

    # Omitted key → preserved
    res = await client.put("/api/attendance/override-bulk", json={
        "year": 2026, "month": 5,
        "entries": [{"date": "2026-05-14", "remark": "改備註"}],
    }, headers=headers)
    assert res.status_code == 200, res.text
    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["late_leave_reason"] == "ASSIGNED_OVERTIME"

    # Explicit null → cleared
    res = await client.put("/api/attendance/override-bulk", json={
        "year": 2026, "month": 5,
        "entries": [{"date": "2026-05-14", "late_leave_reason": None}],
    }, headers=headers)
    assert res.status_code == 200, res.text
    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["late_leave_reason"] is None


@pytest.mark.asyncio
async def test_bulk_override_rejects_invalid_reason(client, db_session):
    await _seed_employee(db_session, emp_id="E921")
    token = _make_token("E921", "EMPLOYEE")
    res = await client.put("/api/attendance/override-bulk", json={
        "year": 2026, "month": 5,
        "entries": [{"date": "2026-05-14", "late_leave_reason": "NOPE"}],
    }, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422
