"""Integration tests for POST /api/auth/change-password."""

from __future__ import annotations

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.rate_limiter import clear_all as clear_rate_limit
from app.models.employee import Employee, Role
from app.utils.password import hash_password


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    clear_rate_limit()
    yield
    clear_rate_limit()


async def _login(
    client: AsyncClient, emp_id: str, password: str
) -> str:
    r = await client.post(
        "/api/auth/login", json={"emp_id": emp_id, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _make_emp(
    session: AsyncSession, emp_id: str, pwd: str = "oldPass1"
) -> Employee:
    e = Employee(
        emp_id=emp_id,
        name="CP",
        department="X",
        role=Role.EMPLOYEE,
        hashed_password=hash_password(pwd),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    session.add(e)
    await session.commit()
    return e


@pytest.mark.asyncio
async def test_change_password_happy_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP001")
    token = await _login(client, "CP001", "oldPass1")

    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["message"]

    # Old password no longer works
    r = await client.post(
        "/api/auth/login", json={"emp_id": "CP001", "password": "oldPass1"}
    )
    assert r.status_code == 401

    # New password works
    r = await client.post(
        "/api/auth/login", json={"emp_id": "CP001", "password": "newPass1"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_wrong_current_password_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP002")
    token = await _login(client, "CP002", "oldPass1")

    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "WRONG", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_no_jwt_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "newPass1"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_weak_new_password_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP003")
    token = await _login(client, "CP003", "oldPass1")

    # Too short
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "short1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422

    # No digit
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "abcdefgh"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_new_equals_current_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP004")
    token = await _login(client, "CP004", "oldPass1")

    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "oldPass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
    assert "differ" in r.json()["detail"]


@pytest.mark.asyncio
async def test_new_equals_emp_id_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # emp_id must be 8+ chars with at least one digit so it passes the schema validator
    await _make_emp(db_session, "EMP1234A")
    token = await _login(client, "EMP1234A", "oldPass1")

    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "EMP1234A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # "EMP1234A" passes schema (8 chars, has digit), so we reach service-layer check
    assert r.status_code == 422
    assert "employee ID" in r.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limit_after_5_wrong_currents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP005")
    token = await _login(client, "CP005", "oldPass1")

    for _ in range(5):
        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": "WRONG", "new_password": "newPass1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401

    # 6th attempt is rate-limited
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "WRONG", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 429
