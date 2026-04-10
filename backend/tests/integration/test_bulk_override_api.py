"""Integration tests for bulk override API endpoint."""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

from app.config import settings
from app.models.employee import Role

_SERVICE = "app.services.attendance_service"


def _make_token(emp_id: str, role: str) -> str:
    payload = {
        "sub": emp_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@pytest.mark.asyncio
async def test_bulk_override_success(client):
    token = _make_token("EMP001", "EMPLOYEE")
    mock_result = {
        "emp_id": "EMP001",
        "updated_count": 1,
        "results": [{"date": "2026-04-01", "first_clock_in": "08:55:00", "last_clock_out": "18:05:00", "status": "NORMAL"}],
    }

    with patch(f"{_SERVICE}.bulk_override_punches", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.put(
            "/api/attendance/override-bulk",
            json={
                "year": 2026,
                "month": 4,
                "entries": [{"date": "2026-04-01", "first_clock_in": "08:55:00", "last_clock_out": "18:05:00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_count"] == 1


@pytest.mark.asyncio
async def test_bulk_override_hr_for_other_employee(client):
    token = _make_token("HR001", "HR")
    mock_result = {
        "emp_id": "EMP001",
        "updated_count": 1,
        "results": [{"date": "2026-04-01", "first_clock_in": "09:00:00", "last_clock_out": "18:00:00", "status": "NORMAL"}],
    }

    with patch(f"{_SERVICE}.bulk_override_punches", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.put(
            "/api/attendance/override-bulk",
            json={
                "year": 2026,
                "month": 4,
                "emp_id": "EMP001",
                "entries": [{"date": "2026-04-01", "first_clock_in": "09:00:00", "last_clock_out": "18:00:00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_bulk_override_unauthenticated(client):
    resp = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026,
            "month": 4,
            "entries": [{"date": "2026-04-01", "first_clock_in": "09:00:00", "last_clock_out": "18:00:00"}],
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bulk_override_empty_entries(client):
    token = _make_token("EMP001", "EMPLOYEE")
    resp = await client.put(
        "/api/attendance/override-bulk",
        json={"year": 2026, "month": 4, "entries": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422  # Validation error: min_length=1


@pytest.mark.asyncio
async def test_bulk_override_permission_error(client):
    token = _make_token("EMP001", "EMPLOYEE")

    with patch(
        f"{_SERVICE}.bulk_override_punches",
        new_callable=AsyncMock,
        side_effect=PermissionError("You cannot override another employee's punches"),
    ):
        resp = await client.put(
            "/api/attendance/override-bulk",
            json={
                "year": 2026,
                "month": 4,
                "emp_id": "EMP002",
                "entries": [{"date": "2026-04-01", "first_clock_in": "09:00:00", "last_clock_out": "18:00:00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 403
