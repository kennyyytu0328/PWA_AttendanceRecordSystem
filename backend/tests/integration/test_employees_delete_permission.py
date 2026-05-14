"""Integration tests for DELETE /api/employees/{emp_id} permission gate.

Task 10: DELETE is ADMIN-only (HR has been revoked).
"""

import datetime
from datetime import UTC, timedelta

import pytest
from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
from app.utils.password import hash_password


def _make_token(emp_id: str, role: Role) -> str:
    """Create a valid JWT token for testing."""
    payload = {
        "sub": emp_id,
        "role": role.value,
        "exp": datetime.datetime.now(UTC) + timedelta(hours=1),
    }
    return jose_jwt.encode(
        payload, settings.secret_key, algorithm=settings.algorithm
    )


async def _seed_employee(
    db_session: AsyncSession,
    emp_id: str,
    role: Role,
) -> Employee:
    emp = Employee(
        emp_id=emp_id,
        name=f"User {emp_id}",
        department="Engineering",
        role=role,
        hashed_password=hash_password("pass1234"),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


class TestDeleteEmployeePermissionGate:
    """DELETE /api/employees/{emp_id} requires ADMIN (not HR)."""

    async def test_hr_delete_forbidden(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """HR is no longer permitted to hard-delete; expect 403."""
        await _seed_employee(db_session, "HR001", Role.HR)
        await _seed_employee(db_session, "EMP001", Role.EMPLOYEE)
        token = _make_token("HR001", Role.HR)

        resp = await client.delete(
            "/api/employees/EMP001",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403

    async def test_admin_delete_passes_permission_check(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """ADMIN passes the permission gate; non-existent target returns 404
        (proves the auth check was satisfied — not 403)."""
        await _seed_employee(db_session, "ADMIN01", Role.ADMIN)
        token = _make_token("ADMIN01", Role.ADMIN)

        resp = await client.delete(
            "/api/employees/GHOST_DOES_NOT_EXIST",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 404
