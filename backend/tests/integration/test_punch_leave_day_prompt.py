"""Punch must not prompt for a LATE/EARLY_LEAVE reason when the day's summary
cannot accept one (registered leave, or a pre-filled clock-out at/after shift
end). Regression for the 2026-08-11 case: half-day 喪假 registered, 12:02
clock-out prompted 「您提前下班」 but ``POST /api/reasons`` rejected the
submission because the summary status was LEAVE.
"""
import datetime
from datetime import UTC, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role
from app.repositories import attendance_repository, summary_repository
from app.services.geolocation_service import WorkModeResult
from app.utils.password import hash_password


def _make_token(emp_id: str, role: Role | str = Role.EMPLOYEE) -> str:
    role_value = role.value if isinstance(role, Role) else role
    payload = {
        "sub": emp_id,
        "role": role_value,
        "exp": datetime.datetime.now(UTC) + timedelta(hours=1),
    }
    return jose_jwt.encode(
        payload, settings.secret_key, algorithm=settings.algorithm
    )


async def _seed_employee(db_session: AsyncSession, emp_id: str) -> Employee:
    emp = Employee(
        emp_id=emp_id,
        name=f"User {emp_id}",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password=hash_password("pass1234"),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def _seed_log(
    db_session: AsyncSession, emp_id: str, timestamp: datetime.datetime
) -> AttendanceLog:
    log = AttendanceLog(
        emp_id=emp_id,
        timestamp=timestamp,
        latitude=25.0330,
        longitude=121.5654,
        accuracy=10.0,
        ip_address="127.0.0.1",
        work_mode=WorkMode.OFFICE,
        is_overridden=False,
    )
    return await attendance_repository.create_log(db_session, log)


_FAKE_GEO_RESULT = WorkModeResult(
    work_mode=WorkMode.OFFICE,
    distance_km=0.02,
    accuracy=10.0,
    is_low_accuracy=False,
)


async def _punch(client: AsyncClient, token: str):
    with patch(
        "app.services.attendance_service.geolocation_service.determine_work_mode",
        new_callable=AsyncMock,
        return_value=_FAKE_GEO_RESULT,
    ):
        return await client.post(
            "/api/attendance/punch",
            json={"latitude": 25.0330, "longitude": 121.5654, "accuracy": 10.0},
            headers={"Authorization": f"Bearer {token}"},
        )


# 2026-08-11 is a Tuesday (workday via weekday fallback — no calendar seeded).
@pytest.mark.asyncio
@freeze_time("2026-08-11 12:02:00")
async def test_leave_day_early_clock_out_does_not_prompt_for_reason(
    client: AsyncClient, db_session: AsyncSession
):
    """A registered 假別 means the day resolves to LEAVE — the punch response
    must not carry tardiness_status/summary_id, or the frontend offers a
    reason form the reason gate is guaranteed to reject.
    """
    await _seed_employee(db_session, "E920")
    morning = datetime.datetime(2026, 8, 11, 7, 44, 0)
    await _seed_log(db_session, "E920", morning)
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E920",
        date=datetime.date(2026, 8, 11),
        first_clock_in=morning,
        last_clock_out=morning,
        status=AttendanceStatus.LEAVE,
        leave_type="喪假",
        remark="4hr(半天)",
    )

    res = await _punch(client, _make_token("E920"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tardiness_status"] is None
    assert body["summary_id"] is None

    # The regenerated summary keeps the leave.
    rows = await summary_repository.find_by_employee(
        db_session, "E920",
        start_date=datetime.date(2026, 8, 11), end_date=datetime.date(2026, 8, 11),
    )
    assert rows and rows[0].status == AttendanceStatus.LEAVE
    assert rows[0].leave_type == "喪假"


@pytest.mark.asyncio
@freeze_time("2026-08-11 12:02:00")
async def test_prefilled_clock_out_day_does_not_prompt_for_reason(
    client: AsyncClient, db_session: AsyncSession
):
    """A pre-filled 18:00 clock-out (monthly-override pre-fill) stays the day's
    MAX punch, so the summary computes NORMAL — the midday punch must not
    prompt for an early-leave reason.
    """
    await _seed_employee(db_session, "E921")
    await _seed_log(
        db_session, "E921", datetime.datetime(2026, 8, 11, 9, 0, 0)
    )
    await _seed_log(
        db_session, "E921", datetime.datetime(2026, 8, 11, 18, 0, 0)
    )

    res = await _punch(client, _make_token("E921"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tardiness_status"] is None
    assert body["summary_id"] is None


@pytest.mark.asyncio
@freeze_time("2026-08-11 12:02:00")
async def test_genuine_early_leave_still_prompts_for_reason(
    client: AsyncClient, db_session: AsyncSession
):
    """No leave, no pre-fill: an on-time clock-in plus a 12:02 clock-out is a
    real EARLY_LEAVE — the prompt (and summary_id) must survive the new gate.
    """
    await _seed_employee(db_session, "E922")
    await _seed_log(
        db_session, "E922", datetime.datetime(2026, 8, 11, 9, 0, 0)
    )

    res = await _punch(client, _make_token("E922"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tardiness_status"] == "EARLY_LEAVE"
    assert body["summary_id"] is not None
