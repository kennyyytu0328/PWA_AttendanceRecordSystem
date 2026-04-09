"""Security hardening tests — Phase 8.

Consolidates and verifies:
1. SQL injection prevention (parameterized queries)
2. Rate limiting on login endpoint
3. CORS configuration
4. Secure response headers
5. No user enumeration (same error for wrong password / non-existent user)
6. JWT expiry validation
7. Input sanitization (Pydantic rejects / strips XSS payloads)
8. Password hashing (never stored in plaintext)
"""

import datetime
import time

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware.rate_limiter import clear_all as clear_rate_limits
from app.models.employee import Employee, Role
from app.repositories.employee_repository import create_employee, find_by_id
from app.utils.password import hash_password, verify_password


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_employee(
    emp_id: str = "EMP001",
    name: str = "Alice Chen",
    department: str = "Engineering",
    role: Role = Role.EMPLOYEE,
    plain_password: str = "secret123",
) -> Employee:
    """Create an Employee model instance with a hashed password."""
    return Employee(
        emp_id=emp_id,
        name=name,
        department=department,
        role=role,
        hashed_password=hash_password(plain_password),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )


def _make_token(
    emp_id: str = "EMP001",
    role: str = "EMPLOYEE",
    expired: bool = False,
    secret: str | None = None,
) -> str:
    """Create a JWT for testing."""
    delta = (
        datetime.timedelta(minutes=-5)
        if expired
        else datetime.timedelta(minutes=30)
    )
    payload = {
        "sub": emp_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.UTC) + delta,
    }
    return jose_jwt.encode(
        payload,
        secret or settings.secret_key,
        algorithm=settings.algorithm,
    )


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Clear rate-limit state before every test."""
    clear_rate_limits()
    yield
    clear_rate_limits()


# =========================================================================
# 1. SQL Injection Prevention
# =========================================================================
class TestSQLInjectionPrevention:
    """Parameterized queries must safely handle injection payloads."""

    async def test_sql_injection_in_emp_id_login(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """SQL injection payload in emp_id should be treated as a literal string,
        returning 401 (not a 500 or a dropped table)."""
        payload = {
            "emp_id": "'; DROP TABLE employees;--",
            "password": "anything",
        }
        resp = await client.post("/api/auth/login", json=payload)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    async def test_sql_injection_in_emp_id_lookup(
        self, db_session: AsyncSession
    ):
        """Repository find_by_id with injection payload returns None, not an error."""
        result = await find_by_id(db_session, "' OR '1'='1")
        assert result is None

    async def test_sql_injection_does_not_destroy_data(
        self, db_session: AsyncSession
    ):
        """After passing injection strings through the repository, existing
        data must remain intact."""
        employee = _make_employee(emp_id="SAFE001")
        await create_employee(db_session, employee)

        # Attempt injection
        await find_by_id(db_session, "'; DROP TABLE employees;--")

        # Original record must still exist
        found = await find_by_id(db_session, "SAFE001")
        assert found is not None
        assert found.emp_id == "SAFE001"


# =========================================================================
# 2. Rate Limiting on Login
# =========================================================================
class TestRateLimiting:
    """Login endpoint must enforce rate limiting after 5 failed attempts."""

    async def test_five_failed_attempts_then_rate_limited(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """After 5 failed logins, the 6th should return 429."""
        payload = {"emp_id": "NOBODY", "password": "wrong"}

        for i in range(5):
            resp = await client.post("/api/auth/login", json=payload)
            assert resp.status_code == 401, f"Attempt {i + 1} should be 401"

        # 6th attempt — rate limited
        resp = await client.post("/api/auth/login", json=payload)
        assert resp.status_code == 429
        assert "Too many" in resp.json()["detail"]

    async def test_successful_login_resets_rate_limit(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A successful login should reset the counter so the user is not
        locked out after a few mistakes."""
        employee = _make_employee(emp_id="EMP_RATE", plain_password="correct")
        await create_employee(db_session, employee)

        # 4 failed attempts (below threshold)
        for _ in range(4):
            resp = await client.post(
                "/api/auth/login",
                json={"emp_id": "EMP_RATE", "password": "wrong"},
            )
            assert resp.status_code == 401

        # Successful login resets counter
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP_RATE", "password": "correct"},
        )
        assert resp.status_code == 200

        # Now 5 more failures should be allowed before 429
        for i in range(5):
            resp = await client.post(
                "/api/auth/login",
                json={"emp_id": "EMP_RATE", "password": "wrong"},
            )
            assert resp.status_code == 401, f"Attempt {i + 1} after reset should be 401"

        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP_RATE", "password": "wrong"},
        )
        assert resp.status_code == 429

    async def test_rate_limit_is_per_emp_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Rate limiting should be scoped per key (IP:emp_id), so one user's
        failures don't block another."""
        # Exhaust limit for user A
        for _ in range(5):
            await client.post(
                "/api/auth/login",
                json={"emp_id": "USER_A", "password": "wrong"},
            )

        # User A is blocked
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "USER_A", "password": "wrong"},
        )
        assert resp.status_code == 429

        # User B should still be allowed
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "USER_B", "password": "wrong"},
        )
        assert resp.status_code == 401  # Not 429


# =========================================================================
# 3. CORS Configuration
# =========================================================================
class TestCORSConfiguration:
    """CORS middleware must be configured with appropriate origins."""

    async def test_cors_allows_configured_origin(self, client: AsyncClient):
        """Preflight request from allowed origin should succeed."""
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    async def test_cors_blocks_unknown_origin(self, client: AsyncClient):
        """Preflight request from unknown origin should not include
        access-control-allow-origin for that origin."""
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        allow_origin = resp.headers.get("access-control-allow-origin")
        assert allow_origin != "http://evil.example.com"

    async def test_cors_allows_expected_methods(self, client: AsyncClient):
        """Preflight should advertise the allowed methods."""
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        for method in ("GET", "POST", "PUT", "DELETE"):
            assert method in allowed

    async def test_cors_allows_auth_header(self, client: AsyncClient):
        """Preflight should allow the Authorization header."""
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allowed_headers = resp.headers.get("access-control-allow-headers", "")
        assert "authorization" in allowed_headers.lower()


# =========================================================================
# 4. Secure Headers
# =========================================================================
class TestSecureHeaders:
    """Every response must include security headers."""

    async def test_x_content_type_options(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    async def test_x_frame_options(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    async def test_x_xss_protection(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-xss-protection") == "1; mode=block"

    async def test_strict_transport_security(self, client: AsyncClient):
        resp = await client.get("/health")
        hsts = resp.headers.get("strict-transport-security", "")
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    async def test_content_security_policy(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("content-security-policy") == "default-src 'self'"

    async def test_security_headers_on_error_responses(self, client: AsyncClient):
        """Security headers should also be present on non-200 responses."""
        resp = await client.get("/api/auth/me")  # 401 — no token
        assert resp.status_code in (401, 403)
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"


# =========================================================================
# 5. No User Enumeration
# =========================================================================
class TestNoUserEnumeration:
    """Login must return the same error for wrong password and non-existent user."""

    async def test_wrong_password_returns_invalid_credentials(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Existing user with wrong password returns generic error."""
        employee = _make_employee(emp_id="EMP_ENUM", plain_password="correct")
        await create_employee(db_session, employee)

        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP_ENUM", "password": "wrong"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    async def test_nonexistent_user_returns_same_error(
        self, client: AsyncClient
    ):
        """Non-existent user returns the exact same error message."""
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "GHOST", "password": "anything"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    async def test_error_messages_are_identical(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Side-by-side comparison: both responses must be structurally identical."""
        employee = _make_employee(emp_id="EMP_COMP", plain_password="correct")
        await create_employee(db_session, employee)

        resp_wrong_pw = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP_COMP", "password": "wrong"},
        )
        resp_no_user = await client.post(
            "/api/auth/login",
            json={"emp_id": "NO_SUCH_USER", "password": "anything"},
        )

        assert resp_wrong_pw.status_code == resp_no_user.status_code
        assert resp_wrong_pw.json()["detail"] == resp_no_user.json()["detail"]


# =========================================================================
# 6. JWT Expiry Validation
# =========================================================================
class TestJWTExpiryValidation:
    """Expired or tampered tokens must be rejected."""

    async def test_expired_token_rejected(self, client: AsyncClient):
        """An expired JWT should produce a 401."""
        token = _make_token(expired=True)
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_token_with_wrong_signature_rejected(self, client: AsyncClient):
        """JWT signed with a different secret should be rejected."""
        token = _make_token(secret="not-the-real-key")
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_valid_token_accepted(self, client: AsyncClient):
        """A properly signed, non-expired token should succeed."""
        token = _make_token(emp_id="EMP_JWT", role="EMPLOYEE")
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["emp_id"] == "EMP_JWT"
        assert data["role"] == "EMPLOYEE"


# =========================================================================
# 7. Input Sanitization (XSS via Pydantic)
# =========================================================================
class TestInputSanitization:
    """XSS payloads in input fields should not cause server errors and
    should be treated as literal strings by Pydantic."""

    async def test_xss_in_emp_id_login(self, client: AsyncClient):
        """XSS payload in emp_id should not crash the server."""
        resp = await client.post(
            "/api/auth/login",
            json={
                "emp_id": "<script>alert('xss')</script>",
                "password": "anything",
            },
        )
        # Should return 401 (invalid credentials), not 500
        assert resp.status_code == 401
        # Response should not reflect the script tag back
        assert "<script>" not in resp.text

    async def test_xss_in_password_login(self, client: AsyncClient):
        """XSS payload in password should not crash the server."""
        resp = await client.post(
            "/api/auth/login",
            json={
                "emp_id": "ANYONE",
                "password": "<img src=x onerror=alert(1)>",
            },
        )
        assert resp.status_code == 401
        assert "onerror" not in resp.text

    async def test_empty_fields_rejected(self, client: AsyncClient):
        """Empty emp_id or password should be rejected by Pydantic validation."""
        resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "", "password": ""},
        )
        assert resp.status_code == 422  # Validation error

    async def test_missing_fields_rejected(self, client: AsyncClient):
        """Missing required fields should return 422."""
        resp = await client.post("/api/auth/login", json={})
        assert resp.status_code == 422


# =========================================================================
# 8. Password Hashing
# =========================================================================
class TestPasswordHashing:
    """Passwords must always be stored as bcrypt hashes, never plaintext."""

    async def test_stored_password_is_hashed(self, db_session: AsyncSession):
        """After creating an employee via the repository, the stored
        hashed_password must not equal the plaintext."""
        employee = _make_employee(emp_id="EMP_HASH", plain_password="my-secret")
        saved = await create_employee(db_session, employee)

        assert saved.hashed_password != "my-secret"
        assert saved.hashed_password.startswith("$2")  # bcrypt prefix

    async def test_password_verifies_against_hash(self, db_session: AsyncSession):
        """The verify_password utility must accept the correct plaintext."""
        employee = _make_employee(emp_id="EMP_VERIFY", plain_password="test-pw")
        saved = await create_employee(db_session, employee)

        assert verify_password("test-pw", saved.hashed_password) is True
        assert verify_password("wrong-pw", saved.hashed_password) is False

    async def test_different_plaintexts_produce_different_hashes(self):
        """Two different passwords should produce different hashes."""
        h1 = hash_password("password-one")
        h2 = hash_password("password-two")
        assert h1 != h2

    async def test_same_plaintext_produces_different_hashes(self):
        """Due to salting, the same password hashed twice should yield
        different hash strings."""
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2  # bcrypt uses random salt

    async def test_employee_response_excludes_password(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """The EmployeeResponse schema must never include the password field."""
        from app.schemas.employee import EmployeeResponse

        employee = _make_employee(emp_id="EMP_RESP", plain_password="hidden")
        await create_employee(db_session, employee)

        response_model = EmployeeResponse.model_validate(employee)
        response_dict = response_model.model_dump()
        assert "password" not in response_dict
        assert "hashed_password" not in response_dict
        assert "plain_password" not in response_dict
