"""Tests for GET /api/attendance/summaries — the monthly-override page editor.

This endpoint backs the monthly-override page, which must always return the
employee's own data regardless of monthly submission state (the whole point
of the page is to prepare data *before* submission).
"""

import datetime
from datetime import UTC, timedelta

from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
from app.utils.password import hash_password


def _make_token(emp_id: str, role: Role | str) -> str:
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


async def test_summaries_returns_unsubmitted_month_data(
    client: AsyncClient, db_session: AsyncSession
):
    """The editor surface must show real punch times for the current month
    even before the employee has submitted it (regression — previously the
    endpoint inherited the 'submitted' default and blanked out the page).
    """
    from app.models.attendance_log import AttendanceLog, WorkMode

    await _seed_employee(db_session, emp_id="E_UNSUB_SUMMARIES")
    # Seed real punch logs so generate_daily_summary computes from them.
    db_session.add_all(
        [
            AttendanceLog(
                emp_id="E_UNSUB_SUMMARIES",
                timestamp=datetime.datetime(2026, 5, 14, 9, 5),
                latitude=25.0,
                longitude=121.5,
                accuracy=10.0,
                ip_address="127.0.0.1",
                work_mode=WorkMode.OFFICE,
            ),
            AttendanceLog(
                emp_id="E_UNSUB_SUMMARIES",
                timestamp=datetime.datetime(2026, 5, 14, 18, 10),
                latitude=25.0,
                longitude=121.5,
                accuracy=10.0,
                ip_address="127.0.0.1",
                work_mode=WorkMode.OFFICE,
            ),
        ]
    )
    await db_session.commit()
    # Deliberately no monthly_submissions row.

    token = _make_token("E_UNSUB_SUMMARIES", Role.EMPLOYEE)
    res = await client.get(
        "/api/attendance/summaries?start_date=2026-05-14&end_date=2026-05-14",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    row = next(r for r in body if r["date"] == "2026-05-14")
    assert row["first_clock_in"] is not None
    assert "09:05" in row["first_clock_in"]
    assert row["last_clock_out"] is not None
    assert "18:10" in row["last_clock_out"]
    assert row["status"] == "NORMAL"


async def test_summaries_includes_leave_type_and_remark(
    client: AsyncClient, db_session: AsyncSession
):
    """leave_type and remark must round-trip through this endpoint so the
    editor can pre-populate them on reload.
    """
    from app.models.daily_attendance_summary import AttendanceStatus
    from app.repositories import summary_repository

    await _seed_employee(db_session, emp_id="E_LEAVE_FIELDS")
    target_date = datetime.date(2026, 5, 14)
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E_LEAVE_FIELDS",
        date=target_date,
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休",
        remark="下午半天",
    )

    token = _make_token("E_LEAVE_FIELDS", Role.EMPLOYEE)
    res = await client.get(
        "/api/attendance/summaries?start_date=2026-05-14&end_date=2026-05-14",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    row = next(r for r in body if r["date"] == "2026-05-14")
    assert row["status"] == "LEAVE"
    assert row["leave_type"] == "特休"
    assert row["remark"] == "下午半天"
