"""Tokens of terminated employees are rejected by the auth middleware.

With week-long access tokens, blocking login alone is not enough — an
already-issued token must stop working as soon as the employee is terminated.
Reactivation restores access for still-unexpired tokens.
"""

from __future__ import annotations

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Role
from app.utils.password import hash_password


async def _make_emp(
    session: AsyncSession, emp_id: str, pwd: str = "oldPass1"
) -> Employee:
    e = Employee(
        emp_id=emp_id,
        name="Term",
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
async def test_token_rejected_after_termination(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    emp = await _make_emp(db_session, "TERM001")

    r = await client.post(
        "/api/auth/login", json={"emp_id": "TERM001", "password": "oldPass1"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200

    emp.terminated_at = datetime.datetime.now(datetime.UTC)
    db_session.add(emp)
    await db_session.commit()

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_token_works_again_after_reactivation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Termination is reversible; reactivating restores unexpired tokens."""
    emp = await _make_emp(db_session, "TERM002")

    r = await client.post(
        "/api/auth/login", json={"emp_id": "TERM002", "password": "oldPass1"}
    )
    token = r.json()["access_token"]

    emp.terminated_at = datetime.datetime.now(datetime.UTC)
    db_session.add(emp)
    await db_session.commit()

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401

    emp.terminated_at = None
    db_session.add(emp)
    await db_session.commit()

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
