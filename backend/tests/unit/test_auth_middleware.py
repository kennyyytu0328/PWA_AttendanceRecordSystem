"""Tests for auth middleware — JWT validation, user injection, role extraction.

TDD RED phase: all tests should FAIL because auth_middleware.py doesn't exist yet.
"""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.config import settings
from app.models.employee import Role


# ---------------------------------------------------------------------------
# Helper: create valid / invalid JWTs
# ---------------------------------------------------------------------------
def _make_token(
    emp_id: str = "EMP001",
    role: str = "EMPLOYEE",
    expired: bool = False,
    secret: str | None = None,
) -> str:
    payload = {
        "sub": emp_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.UTC)
        + (
            datetime.timedelta(minutes=-5)
            if expired
            else datetime.timedelta(minutes=30)
        ),
    }
    return jwt.encode(payload, secret or settings.secret_key, algorithm=settings.algorithm)


# ---------------------------------------------------------------------------
# Fixtures: minimal FastAPI app with a protected route
# ---------------------------------------------------------------------------
@pytest.fixture
def protected_app():
    """Create a minimal FastAPI app with one protected route using the middleware."""
    from app.middleware.auth_middleware import get_current_user

    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected_route(user: dict = Depends(get_current_user)):
        return {"emp_id": user["sub"], "role": user["role"]}

    return test_app


@pytest.fixture
async def protected_client(protected_app):
    async with AsyncClient(
        transport=ASGITransport(app=protected_app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestAuthMiddleware:
    """JWT validation and user extraction."""

    async def test_valid_token_extracts_user(self, protected_client: AsyncClient):
        """A valid JWT should inject user payload into the route."""
        token = _make_token(emp_id="EMP001", role="EMPLOYEE")
        resp = await protected_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["emp_id"] == "EMP001"
        assert data["role"] == "EMPLOYEE"

    async def test_missing_authorization_header(self, protected_client: AsyncClient):
        """Request with no Authorization header should return 401."""
        resp = await protected_client.get("/protected")
        assert resp.status_code == 401
        assert "Not authenticated" in resp.json()["detail"]

    async def test_invalid_scheme(self, protected_client: AsyncClient):
        """Non-Bearer scheme should return 401."""
        token = _make_token()
        resp = await protected_client.get(
            "/protected",
            headers={"Authorization": f"Basic {token}"},
        )
        assert resp.status_code == 401

    async def test_expired_token(self, protected_client: AsyncClient):
        """Expired JWT should return 401."""
        token = _make_token(expired=True)
        resp = await protected_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower() or "token" in resp.json()["detail"].lower()

    async def test_invalid_signature(self, protected_client: AsyncClient):
        """Token signed with wrong secret should return 401."""
        token = _make_token(secret="wrong-secret-key")
        resp = await protected_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_malformed_token(self, protected_client: AsyncClient):
        """Completely malformed token should return 401."""
        resp = await protected_client.get(
            "/protected",
            headers={"Authorization": "Bearer not-a-jwt-at-all"},
        )
        assert resp.status_code == 401


class TestRequireRole:
    """Role-based route protection via require_role dependency."""

    @pytest.fixture
    def role_app(self):
        from app.middleware.auth_middleware import get_current_user, require_role

        test_app = FastAPI()

        @test_app.get("/admin-only")
        async def admin_route(user: dict = require_role(Role.ADMIN)):
            return {"emp_id": user["sub"], "role": user["role"]}

        @test_app.get("/hr-plus")
        async def hr_route(user: dict = require_role(Role.HR)):
            return {"emp_id": user["sub"], "role": user["role"]}

        @test_app.get("/manager-plus")
        async def manager_route(user: dict = require_role(Role.MANAGER)):
            return {"emp_id": user["sub"], "role": user["role"]}

        return test_app

    @pytest.fixture
    async def role_client(self, role_app):
        async with AsyncClient(
            transport=ASGITransport(app=role_app),
            base_url="http://test",
        ) as ac:
            yield ac

    async def test_admin_can_access_admin_route(self, role_client: AsyncClient):
        """ADMIN role should access admin-only routes."""
        token = _make_token(role="ADMIN")
        resp = await role_client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "ADMIN"

    async def test_employee_cannot_access_admin_route(self, role_client: AsyncClient):
        """EMPLOYEE role should be denied access to admin-only routes (403)."""
        token = _make_token(role="EMPLOYEE")
        resp = await role_client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_hr_can_access_hr_route(self, role_client: AsyncClient):
        """HR role should access HR+ routes."""
        token = _make_token(role="HR")
        resp = await role_client.get(
            "/hr-plus",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    async def test_admin_can_access_hr_route(self, role_client: AsyncClient):
        """ADMIN (higher than HR) should access HR+ routes."""
        token = _make_token(role="ADMIN")
        resp = await role_client.get(
            "/hr-plus",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    async def test_employee_cannot_access_manager_route(self, role_client: AsyncClient):
        """EMPLOYEE role should be denied access to manager+ routes (403)."""
        token = _make_token(role="EMPLOYEE")
        resp = await role_client.get(
            "/manager-plus",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_manager_can_access_manager_route(self, role_client: AsyncClient):
        """MANAGER role should access manager+ routes."""
        token = _make_token(role="MANAGER")
        resp = await role_client.get(
            "/manager-plus",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
