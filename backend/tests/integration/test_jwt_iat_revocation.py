"""JWT revocation via password_changed_at vs iat."""

from __future__ import annotations

import datetime
import time

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
        name="Rev",
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
async def test_old_jwt_rejected_after_password_change(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "REV001")

    # Step 1: get a JWT
    r = await client.post(
        "/api/auth/login", json={"emp_id": "REV001", "password": "oldPass1"}
    )
    assert r.status_code == 200
    old_token = r.json()["access_token"]

    # Step 2: confirm /me works with it
    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert r.status_code == 200

    # Step 3: change password (ensure at least 1 second elapses so iat < now)
    time.sleep(1)
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert r.status_code == 200

    # Step 4: old JWT is now revoked
    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_new_jwt_after_change_still_works(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "REV002")

    r = await client.post(
        "/api/auth/login", json={"emp_id": "REV002", "password": "oldPass1"}
    )
    old_token = r.json()["access_token"]
    time.sleep(1)
    await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {old_token}"},
    )

    # Login again with new password
    r = await client.post(
        "/api/auth/login", json={"emp_id": "REV002", "password": "newPass1"}
    )
    assert r.status_code == 200
    new_token = r.json()["access_token"]

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_legacy_employee_no_password_changed_at_still_works(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An employee created before this feature has password_changed_at = NULL.
    Their existing JWTs must continue to validate.
    """
    await _make_emp(db_session, "REV003")
    # password_changed_at is NULL by default

    r = await client.post(
        "/api/auth/login", json={"emp_id": "REV003", "password": "oldPass1"}
    )
    token = r.json()["access_token"]

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
