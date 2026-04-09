"""Integration tests for the Attendance Router (Phase 4C).

Tests mock ``attendance_service`` functions at the router level so that
we exercise HTTP handling, auth, role checks, and serialisation without
needing a real database or geolocation service.
"""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

from app.config import settings
from app.models.attendance_log import AttendanceLog, WorkMode
from app.services.attendance_service import PunchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token(emp_id: str, role: str) -> str:
    """Create a valid JWT for testing."""
    payload = {
        "sub": emp_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _fake_log(
    *,
    log_id: int = 1,
    emp_id: str = "EMP001",
    work_mode: WorkMode = WorkMode.OFFICE,
    is_overridden: bool = False,
) -> AttendanceLog:
    """Build a fake ``AttendanceLog`` for mocking service returns."""
    return AttendanceLog(
        id=log_id,
        emp_id=emp_id,
        timestamp=datetime.datetime.now(datetime.UTC),
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="127.0.0.1",
        work_mode=work_mode,
        is_overridden=is_overridden,
    )


def _fake_punch_result(*, emp_id: str = "EMP001") -> PunchResult:
    """Build a fake ``PunchResult`` for mocking the punch service call."""
    return PunchResult(
        log=_fake_log(emp_id=emp_id),
        work_mode=WorkMode.OFFICE,
        distance_km=0.05,
        is_low_accuracy=False,
    )


_SERVICE = "app.routers.attendance.attendance_service"


# ---------------------------------------------------------------------------
# 1. Punch — success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_punch_success(client):
    token = _make_token("EMP001", "EMPLOYEE")
    mock_result = _fake_punch_result()

    with patch(f"{_SERVICE}.punch", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.post(
            "/api/attendance/punch",
            json={"latitude": 25.033, "longitude": 121.565, "accuracy": 10.0},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["work_mode"] == "OFFICE"
    assert body["distance_km"] == 0.05
    assert body["is_low_accuracy"] is False


# ---------------------------------------------------------------------------
# 2. Punch — no auth → 401
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_punch_no_auth_returns_401(client):
    resp = await client.post(
        "/api/attendance/punch",
        json={"latitude": 25.033, "longitude": 121.565, "accuracy": 10.0},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Punch — invalid body → 422
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_punch_invalid_data_returns_422(client):
    token = _make_token("EMP001", "EMPLOYEE")
    resp = await client.post(
        "/api/attendance/punch",
        json={"latitude": 999, "longitude": 121.565, "accuracy": 10.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Get today's logs — returns list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_today_logs(client):
    token = _make_token("EMP001", "EMPLOYEE")
    fake_logs = [_fake_log(), _fake_log(log_id=2)]

    with patch(
        f"{_SERVICE}.get_today_punches",
        new_callable=AsyncMock,
        return_value=fake_logs,
    ):
        resp = await client.get(
            "/api/attendance/today",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# 5. Get history with date range
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_history_with_date_range(client):
    token = _make_token("EMP001", "EMPLOYEE")
    fake_logs = [_fake_log()]

    with patch(
        f"{_SERVICE}.get_history",
        new_callable=AsyncMock,
        return_value=fake_logs,
    ):
        resp = await client.get(
            "/api/attendance",
            params={"start_date": "2026-03-01", "end_date": "2026-03-19"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# 6. Get team logs — MANAGER role, returns list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_team_logs_as_manager(client):
    token = _make_token("MGR001", "MANAGER")
    fake_logs = [_fake_log(emp_id="EMP001"), _fake_log(log_id=2, emp_id="EMP002")]

    with patch(
        f"{_SERVICE}.get_team_logs",
        new_callable=AsyncMock,
        return_value=fake_logs,
    ):
        resp = await client.get(
            "/api/attendance/team",
            params={"start_date": "2026-03-19", "end_date": "2026-03-19"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# 7. Get team logs — EMPLOYEE role → 403
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_team_logs_forbidden_for_employee(client):
    token = _make_token("EMP001", "EMPLOYEE")

    resp = await client.get(
        "/api/attendance/team",
        params={"start_date": "2026-03-19", "end_date": "2026-03-19"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 8. Get all logs — HR role, returns list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_all_logs_as_hr(client):
    token = _make_token("HR001", "HR")
    fake_logs = [_fake_log(emp_id="EMP001"), _fake_log(log_id=2, emp_id="EMP002")]

    with patch(
        f"{_SERVICE}.get_all_logs",
        new_callable=AsyncMock,
        return_value=fake_logs,
    ):
        resp = await client.get(
            "/api/attendance/all",
            params={"start_date": "2026-03-19", "end_date": "2026-03-19"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# 9. Get all logs — EMPLOYEE role → 403
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_all_logs_forbidden_for_employee(client):
    token = _make_token("EMP001", "EMPLOYEE")

    resp = await client.get(
        "/api/attendance/all",
        params={"start_date": "2026-03-19", "end_date": "2026-03-19"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 10. Override punch — MANAGER role
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_override_punch_as_manager(client):
    token = _make_token("MGR001", "MANAGER")
    fake_log = _fake_log(is_overridden=True)

    with patch(
        f"{_SERVICE}.override_attendance",
        new_callable=AsyncMock,
        return_value=fake_log,
    ):
        resp = await client.post(
            "/api/attendance/override",
            json={
                "target_emp_id": "EMP001",
                "latitude": 25.033,
                "longitude": 121.565,
                "accuracy": 10.0,
                "work_mode": "OFFICE",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_overridden"] is True
