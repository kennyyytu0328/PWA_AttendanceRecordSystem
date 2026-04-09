"""Integration tests for the system config router.

TDD RED phase: tests written before the router implementation.
Uses the shared conftest.py fixtures (client, db_session, setup_db).
"""

import datetime

import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import settings


# ---------------------------------------------------------------------------
# Helper: create a JWT token for a given role
# ---------------------------------------------------------------------------
def _make_token(emp_id: str, role: str) -> str:
    payload = {
        "sub": emp_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _auth_header(emp_id: str, role: str) -> dict[str, str]:
    token = _make_token(emp_id, role)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /api/config/office-location
# ---------------------------------------------------------------------------
class TestGetOfficeLocation:
    """GET /api/config/office-location — any authenticated user."""

    async def test_returns_null_when_not_set(self, client: AsyncClient):
        """Should return null value when office location has not been configured."""
        resp = await client.get(
            "/api/config/office-location",
            headers=_auth_header("EMP001", "EMPLOYEE"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "office_location"
        assert data["value"] is None

    async def test_returns_location_after_setting(
        self, client: AsyncClient, db_session
    ):
        """Should return the office location after it has been set."""
        location = {"latitude": 25.033, "longitude": 121.565}

        # Set it first (as HR)
        put_resp = await client.put(
            "/api/config/office-location",
            json=location,
            headers=_auth_header("HR001", "HR"),
        )
        assert put_resp.status_code == 200

        # Now GET it (as EMPLOYEE)
        get_resp = await client.get(
            "/api/config/office-location",
            headers=_auth_header("EMP001", "EMPLOYEE"),
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["key"] == "office_location"
        assert data["value"]["latitude"] == 25.033
        assert data["value"]["longitude"] == 121.565

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        """Should return 401 when no token is provided."""
        resp = await client.get("/api/config/office-location")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/config/office-location
# ---------------------------------------------------------------------------
class TestSetOfficeLocation:
    """PUT /api/config/office-location — HR+ role required."""

    async def test_set_office_location_success_hr(self, client: AsyncClient):
        """HR should be able to set the office location."""
        location = {"latitude": 25.033, "longitude": 121.565}
        resp = await client.put(
            "/api/config/office-location",
            json=location,
            headers=_auth_header("HR001", "HR"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "office_location"
        assert data["value"]["latitude"] == 25.033
        assert data["value"]["longitude"] == 121.565
        assert data["updated_by"] == "HR001"

    async def test_set_office_location_forbidden_employee(self, client: AsyncClient):
        """EMPLOYEE should be forbidden from setting office location."""
        location = {"latitude": 25.033, "longitude": 121.565}
        resp = await client.put(
            "/api/config/office-location",
            json=location,
            headers=_auth_header("EMP001", "EMPLOYEE"),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/config/{key} — ADMIN only
# ---------------------------------------------------------------------------
class TestGetConfigByKey:
    """GET /api/config/{key} — ADMIN only."""

    async def test_get_config_by_key_admin(self, client: AsyncClient):
        """ADMIN should be able to read any config key."""
        # First set a config value
        await client.put(
            "/api/config/some_setting",
            json={"key": "some_setting", "value": {"feature_flag": True}},
            headers=_auth_header("ADMIN01", "ADMIN"),
        )

        resp = await client.get(
            "/api/config/some_setting",
            headers=_auth_header("ADMIN01", "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "some_setting"
        assert data["value"]["feature_flag"] is True

    async def test_get_config_returns_null_for_missing_key(self, client: AsyncClient):
        """Should return null value for a config key that does not exist."""
        resp = await client.get(
            "/api/config/nonexistent_key",
            headers=_auth_header("ADMIN01", "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "nonexistent_key"
        assert data["value"] is None

    async def test_get_config_forbidden_for_non_admin(self, client: AsyncClient):
        """HR should be forbidden from reading arbitrary config keys."""
        resp = await client.get(
            "/api/config/some_setting",
            headers=_auth_header("HR001", "HR"),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/config/{key} — ADMIN only
# ---------------------------------------------------------------------------
class TestSetConfigByKey:
    """PUT /api/config/{key} — ADMIN only."""

    async def test_set_config_by_key_admin(self, client: AsyncClient):
        """ADMIN should be able to set any config key."""
        resp = await client.put(
            "/api/config/max_radius",
            json={"key": "max_radius", "value": {"meters": 200}},
            headers=_auth_header("ADMIN01", "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "max_radius"
        assert data["value"]["meters"] == 200
        assert data["updated_by"] == "ADMIN01"
