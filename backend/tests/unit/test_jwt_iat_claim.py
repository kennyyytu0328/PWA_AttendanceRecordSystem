"""Verify both JWT issuance paths set the `iat` claim."""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
from app.repositories.employee_repository import create_employee
from app.services import employee_service
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
