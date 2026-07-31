"""Tests for clearing leave_type / remark via bulk override (explicit null).

An explicit JSON ``null`` for leave_type / remark / overtime_hours means
"clear the stored value"; omitting the key entirely means "leave it alone".
Regression coverage for the bug where clearing a submitted leave_type on the
monthly-override page silently round-tripped the old value back.
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
async def test_explicit_null_clears_leave_and_remark(
    client: AsyncClient, db_session: AsyncSession
):
    """Explicit null leave_type/remark clears them; status recomputes."""
    await _seed_employee(db_session, emp_id="E200")
    token = _make_token("E200", "EMPLOYEE")
    headers = {"Authorization": f"Bearer {token}"}

    # Set punches + leave (the mistaken submission)
    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [{
                "date": "2026-05-14",
                "first_clock_in": "09:00",
                "last_clock_out": "18:00",
                "leave_type": "出差",
                "remark": "全天",
            }],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["status"] == "LEAVE"
    assert row["leave_type"] == "出差"

    # Clear via explicit nulls (what the frontend sends for emptied fields)
    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [{
                "date": "2026-05-14",
                "first_clock_in": "09:00",
                "last_clock_out": "18:00",
                "leave_type": None,
                "remark": None,
            }],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text

    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["leave_type"] is None
    assert row["remark"] is None
    assert row["status"] == "NORMAL"  # recomputed from on-time punches


@pytest.mark.asyncio
async def test_omitted_fields_preserve_leave(
    client: AsyncClient, db_session: AsyncSession
):
    """Entries that omit leave_type/remark keys leave stored values alone."""
    await _seed_employee(db_session, emp_id="E201")
    token = _make_token("E201", "EMPLOYEE")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [{
                "date": "2026-05-14",
                "leave_type": "特休",
                "remark": "上午",
            }],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text

    # Punch-only entry with no leave_type / remark keys at all
    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [{
                "date": "2026-05-14",
                "first_clock_in": "09:00",
                "last_clock_out": "18:00",
            }],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text

    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["leave_type"] == "特休"
    assert row["remark"] == "上午"
    assert row["status"] == "LEAVE"  # leave still takes priority


@pytest.mark.asyncio
async def test_clear_leave_on_no_punch_day_becomes_absent(
    client: AsyncClient, db_session: AsyncSession
):
    """Clearing the leave on a punchless workday must not strand a LEAVE row."""
    await _seed_employee(db_session, emp_id="E202")
    token = _make_token("E202", "EMPLOYEE")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [{"date": "2026-05-14", "leave_type": "特休"}],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["status"] == "LEAVE"

    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [{
                "date": "2026-05-14",
                "leave_type": None,
                "remark": None,
            }],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text

    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["leave_type"] is None
    assert row["status"] == "ABSENT"  # no punches, no leave, workday
