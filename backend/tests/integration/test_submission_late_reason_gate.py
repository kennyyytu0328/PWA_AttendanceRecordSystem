"""Submission gate: missing late-leave reasons block POST /api/monthly-submissions.

A workday whose last clock-out runs past shift end without a filled
``late_leave_reason`` must not be submittable — mirrors the frontend
hard-block added in Task 12. See CLAUDE.md for the late-leave-reason design.
"""

import datetime
from datetime import UTC, timedelta

import pytest
from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.employee import Employee, Role
from app.models.daily_attendance_summary import AttendanceStatus
from app.repositories import summary_repository
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
async def test_submit_blocked_when_reason_missing(client: AsyncClient, db_session: AsyncSession):
    await _seed_employee(db_session, "E930")
    token = _make_token("E930", "EMPLOYEE")
    d = datetime.date(2026, 7, 22)  # Wednesday workday
    await summary_repository.upsert_summary(
        db_session, emp_id="E930", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(9, 0)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(19, 0)),
        status=AttendanceStatus.NORMAL,
    )
    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E930", "year": 2026, "month": 7},
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "late_reason_missing"
    assert "2026-07-22" in detail["dates"]


@pytest.mark.asyncio
async def test_submit_ok_when_reason_filled_or_exempt(client: AsyncClient, db_session: AsyncSession):
    await _seed_employee(db_session, "E931")
    token = _make_token("E931", "EMPLOYEE")
    mk = lambda day, **kw: summary_repository.upsert_summary(  # noqa: E731
        db_session, emp_id="E931", date=datetime.date(2026, 7, day), **kw)
    dt = lambda day, h, m: datetime.datetime.combine(  # noqa: E731
        datetime.date(2026, 7, day), datetime.time(h, m))

    # late clock-out but reason filled -> OK
    await mk(22, first_clock_in=dt(22, 9, 0), last_clock_out=dt(22, 19, 0),
             status=AttendanceStatus.NORMAL, late_leave_reason="PERSONAL")
    # on-time 18:00 exactly -> exempt
    await mk(23, first_clock_in=dt(23, 9, 0), last_clock_out=dt(23, 18, 0),
             status=AttendanceStatus.NORMAL)
    # leave day (特休 not in required list) with late clock-out -> exempt
    await mk(24, first_clock_in=dt(24, 9, 0), last_clock_out=dt(24, 19, 0),
             status=AttendanceStatus.LEAVE, leave_type="特休")
    # single punch (first == last) -> exempt (no clock-out yet)
    await mk(27, first_clock_in=dt(27, 19, 0), last_clock_out=dt(27, 19, 0),
             status=AttendanceStatus.LATE)

    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E931", "year": 2026, "month": 7},
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_same_minute_clockout_with_seconds_is_on_time(client: AsyncClient, db_session: AsyncSession):
    """18:00:22 against an 18:00 shift end is on time — the gate must use
    minute precision, matching the "HH:MM" comparison the frontend shows."""
    await _seed_employee(db_session, "E933")
    token = _make_token("E933", "EMPLOYEE")
    d = datetime.date(2026, 7, 22)
    await summary_repository.upsert_summary(
        db_session, emp_id="E933", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(9, 0)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(18, 0, 22)),
        status=AttendanceStatus.NORMAL,
    )
    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E933", "year": 2026, "month": 7},
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_gate_catches_punches_with_no_summary_row(client: AsyncClient, db_session: AsyncSession):
    """Direct API submission for a month never opened in the UI: raw punch
    logs exist but no summary was materialized. The gate must regenerate
    summaries from the logs instead of scanning an empty table."""
    await _seed_employee(db_session, "E934")
    token = _make_token("E934", "EMPLOYEE")
    d = datetime.date(2026, 7, 22)  # Wednesday workday
    for t in (datetime.time(9, 0), datetime.time(19, 0)):
        db_session.add(AttendanceLog(
            emp_id="E934",
            timestamp=datetime.datetime.combine(d, t),
            latitude=25.0,
            longitude=121.5,
            accuracy=10.0,
            ip_address="127.0.0.1",
            work_mode=WorkMode.OFFICE,
        ))
    await db_session.commit()

    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E934", "year": 2026, "month": 7},
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "late_reason_missing"
    assert "2026-07-22" in detail["dates"]


@pytest.mark.asyncio
async def test_submit_blocked_on_business_trip_late_clockout(client: AsyncClient, db_session: AsyncSession):
    await _seed_employee(db_session, "E932")
    token = _make_token("E932", "EMPLOYEE")
    d = datetime.date(2026, 7, 22)
    await summary_repository.upsert_summary(
        db_session, emp_id="E932", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(9, 0)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(19, 0)),
        status=AttendanceStatus.LEAVE, leave_type="出差",
    )
    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E932", "year": 2026, "month": 7},
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "late_reason_missing"
