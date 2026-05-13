"""Verify both JWT issuance paths set the `iat` claim."""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
from app.repositories.employee_repository import create_employee
from app.services import employee_service, webauthn_service
from app.utils.password import hash_password


@pytest.mark.asyncio
async def test_password_login_sets_iat(db_session: AsyncSession) -> None:
    """Password login must set iat claim in the JWT."""
    employee = Employee(
        emp_id="IAT001",
        name="IAT User",
        department="X",
        role=Role.EMPLOYEE,
        hashed_password=hash_password("pass1234"),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    await create_employee(db_session, employee)

    result = await employee_service.authenticate(db_session, "IAT001", "pass1234")

    payload: dict[str, Any] = jose_jwt.decode(
        result.access_token, settings.secret_key, algorithms=[settings.algorithm]
    )
    assert "iat" in payload
    assert isinstance(payload["iat"], int)


@pytest.mark.asyncio
async def test_webauthn_login_sets_iat(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """WebAuthn authenticate/verify path must also set iat claim on the issued JWT."""
    employee = Employee(
        emp_id="IAT002",
        name="WA User",
        department="X",
        role=Role.EMPLOYEE,
        hashed_password=hash_password("pass1234"),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    await create_employee(db_session, employee)

    # Seed a fake pending challenge so the handler won't bail early
    webauthn_service._challenges["IAT002"] = b"\x00" * 32

    # Patch verify_authentication to return the emp_id without real WebAuthn
    async def fake_verify(
        session: AsyncSession,
        credential_id: str,
        body: dict,
        challenge: bytes,
    ) -> str:
        return "IAT002"

    with patch.object(webauthn_service, "verify_authentication", side_effect=fake_verify):
        resp = await client.post(
            "/api/auth/authenticate/verify",
            json={"id": "fake-credential-id", "emp_id": "IAT002"},
        )

    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]

    payload: dict[str, Any] = jose_jwt.decode(
        token, settings.secret_key, algorithms=[settings.algorithm]
    )
    assert "iat" in payload, "WebAuthn-issued JWT must contain 'iat' claim"
    assert isinstance(payload["iat"], int)
