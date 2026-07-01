"""Integration tests for POST /api/nfc/import."""

import datetime

import pytest

from app.config import settings
from app.models.employee import Employee, Role


def _make_employee(emp_id: str = "F1000118") -> Employee:
    return Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )


def _cp950(rows: list[str]) -> bytes:
    return ("\n".join(rows) + "\n").encode("cp950")


@pytest.mark.asyncio
async def test_import_missing_key_is_401(client, monkeypatch):
    monkeypatch.setattr(settings, "nfc_import_api_key", "secret-key")
    resp = await client.post("/api/nfc/import", content=_cp950([]))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_wrong_key_is_401(client, monkeypatch):
    monkeypatch.setattr(settings, "nfc_import_api_key", "secret-key")
    resp = await client.post(
        "/api/nfc/import",
        content=_cp950([]),
        headers={"X-NFC-API-Key": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_not_configured_is_503(client, monkeypatch):
    monkeypatch.setattr(settings, "nfc_import_api_key", "")
    resp = await client.post(
        "/api/nfc/import",
        content=_cp950([]),
        headers={"X-NFC-API-Key": "anything"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_import_success(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "nfc_import_api_key", "secret-key")
    db_session.add(_make_employee())
    await db_session.commit()

    body = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,181045,F1000118,2,5717003342,王小明",
    ])
    resp = await client.post(
        "/api/nfc/import",
        content=body,
        headers={"X-NFC-API-Key": "secret-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filled_in"] == 1
    assert data["filled_out"] == 1
    assert data["affected_days"] == ["F1000118 2026-07-01"]
