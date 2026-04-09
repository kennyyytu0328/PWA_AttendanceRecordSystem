"""Integration tests for the authentication router.

TDD RED phase: tests should FAIL because routers/auth.py doesn't exist yet.
Uses the shared conftest.py fixtures (client, db_session, setup_db).
"""

import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models.employee import Employee, Role
from app.utils.password import hash_password


# ---------------------------------------------------------------------------
# Helper: seed an employee into the test DB
# ---------------------------------------------------------------------------
async def _seed_employee(
    db_session,
    emp_id: str = "EMP001",
    password: str = "securepass123",
    role: Role = Role.EMPLOYEE,
) -> Employee:
    emp = Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=role,
        hashed_password=hash_password(password),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


# ---------------------------------------------------------------------------
# Login Tests
# ---------------------------------------------------------------------------
class TestLoginEndpoint:
    """POST /api/auth/login"""

    async def test_login_success(self, client: AsyncClient, db_session):
        """Valid credentials should return a JWT access_token."""
        await _seed_employee(db_session)
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP001", "password": "securepass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, db_session):
        """Wrong password should return 401 with no user-enumeration hint."""
        await _seed_employee(db_session)
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP001", "password": "wrongpass"},
        )
        assert resp.status_code == 401
        assert "Invalid credentials" in resp.json()["detail"]

    async def test_login_nonexistent_user(self, client: AsyncClient, db_session):
        """Non-existent user should return 401 (same error as wrong password)."""
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "GHOST", "password": "anypass"},
        )
        assert resp.status_code == 401
        assert "Invalid credentials" in resp.json()["detail"]

    async def test_login_empty_fields(self, client: AsyncClient):
        """Empty emp_id or password should return 422 validation error."""
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "", "password": ""},
        )
        assert resp.status_code == 422

    async def test_login_missing_fields(self, client: AsyncClient):
        """Missing required fields should return 422."""
        resp = await client.post("/api/auth/login", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Token / Protected route Tests
# ---------------------------------------------------------------------------
class TestTokenFlow:
    """Verify tokens from login work for protected endpoints."""

    async def test_token_grants_access(self, client: AsyncClient, db_session):
        """Token from login should authenticate subsequent requests."""
        await _seed_employee(db_session)
        login_resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP001", "password": "securepass123"},
        )
        token = login_resp.json()["access_token"]

        # GET /api/auth/me — returns current user info
        me_resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        data = me_resp.json()
        assert data["emp_id"] == "EMP001"
        assert data["role"] == "EMPLOYEE"

    async def test_me_without_token(self, client: AsyncClient):
        """GET /api/auth/me without token should return 401."""
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# WebAuthn Registration Options
# ---------------------------------------------------------------------------
class TestWebAuthnRegistration:
    """POST /api/auth/register/generate-options"""

    async def test_generate_registration_options(
        self, client: AsyncClient, db_session
    ):
        """Should return WebAuthn registration options JSON for an authenticated user."""
        await _seed_employee(db_session)
        login_resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP001", "password": "securepass123"},
        )
        token = login_resp.json()["access_token"]

        with patch(
            "app.routers.auth.webauthn_service.generate_registration_options",
            new_callable=AsyncMock,
            return_value='{"challenge": "test"}',
        ):
            resp = await client.post(
                "/api/auth/register/generate-options",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert "challenge" in resp.json()


# ---------------------------------------------------------------------------
# WebAuthn Authentication Options
# ---------------------------------------------------------------------------
class TestWebAuthnAuthentication:
    """POST /api/auth/authenticate/generate-options"""

    async def test_generate_authentication_options(
        self, client: AsyncClient, db_session
    ):
        """Should return WebAuthn authentication options for a known employee."""
        await _seed_employee(db_session)

        with patch(
            "app.routers.auth.webauthn_service.generate_authentication_options",
            new_callable=AsyncMock,
            return_value='{"challenge": "auth-test"}',
        ):
            resp = await client.post(
                "/api/auth/authenticate/generate-options",
                json={"emp_id": "EMP001"},
            )
        assert resp.status_code == 200
        assert "challenge" in resp.json()
