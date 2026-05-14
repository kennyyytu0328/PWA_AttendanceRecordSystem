"""Tests for bulk override with leave_type / remark (Task 15)."""

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
    shift_start_time: datetime.time = datetime.time(9, 0),
    shift_end_time: datetime.time = datetime.time(18, 0),
) -> Employee:
    role_enum = role if isinstance(role, Role) else Role(role)
    emp = Employee(
        emp_id=emp_id,
        name=f"User {emp_id}",
        department="Engineering",
        role=role_enum,
        hashed_password=hash_password("pass1234"),
        shift_start_time=shift_start_time,
        shift_end_time=shift_end_time,
    )
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


@pytest.mark.asyncio
async def test_bulk_override_with_leave_type_sets_LEAVE_status(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, emp_id="E100")
    token = _make_token("E100", "EMPLOYEE")
    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [
                {"date": "2026-05-14", "leave_type": "特休", "remark": "上午"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text

    # Seed monthly submission so the row isn't filtered out by submission_filter
    from app.repositories import monthly_submission_repository
    await monthly_submission_repository.upsert(
        db_session, emp_id="E100", year=2026, month=5
    )

    summary_res = await client.get(
        "/api/attendance/summaries?start_date=2026-05-14&end_date=2026-05-14",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary_res.status_code == 200, summary_res.text
    body = summary_res.json()
    row = next(r for r in body if r["date"] == "2026-05-14")
    assert row["status"] == "LEAVE"


@pytest.mark.asyncio
async def test_bulk_override_remark_only_keeps_normal_status(
    client: AsyncClient, db_session: AsyncSession
):
    """If only remark is set (no leave_type), status reflects punches normally."""
    await _seed_employee(
        db_session, emp_id="E101",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    token = _make_token("E101", "EMPLOYEE")
    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [{
                "date": "2026-05-14",
                "first_clock_in": "09:00",
                "last_clock_out": "18:00",
                "remark": "做了個提醒",
            }],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text

    # Seed submission so reports row is visible
    from app.repositories import monthly_submission_repository
    await monthly_submission_repository.upsert(
        db_session, emp_id="E101", year=2026, month=5
    )

    summary_res = await client.get(
        "/api/attendance/summaries?start_date=2026-05-14&end_date=2026-05-14",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary_res.status_code == 200, summary_res.text
    body = summary_res.json()
    row = next(r for r in body if r["date"] == "2026-05-14")
    assert row["status"] == "NORMAL"
