"""Integration tests for the employee router.

TDD RED phase: tests should FAIL because routers/employees.py doesn't exist yet.
Uses the shared conftest.py fixtures (client, db_session, setup_db).
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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
    emp_id: str = "EMP001",
    name: str = "Test User",
    department: str = "Engineering",
    role: Role = Role.EMPLOYEE,
    password: str = "securepass123",
) -> Employee:
    """Insert an employee directly into the test DB."""
    emp = Employee(
        emp_id=emp_id,
        name=name,
        department=department,
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
# POST /api/employees — Create employee
# ---------------------------------------------------------------------------
class TestCreateEmployee:
    """POST /api/employees"""

    async def test_create_employee_success_hr(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """HR role should be able to create a new employee."""
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        token = _make_token("HR001", Role.HR)

        resp = await client.post(
            "/api/employees",
            json={
                "emp_id": "NEW001",
                "name": "New Employee",
                "department": "Sales",
                "role": "EMPLOYEE",
                "password": "newpass123",
                "shift_start_time": "09:00:00",
                "shift_end_time": "18:00:00",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["emp_id"] == "NEW001"
        assert data["name"] == "New Employee"
        assert data["department"] == "Sales"
        assert data["role"] == "EMPLOYEE"
        # Password should NOT be in response
        assert "password" not in data
        assert "hashed_password" not in data

    async def test_create_employee_forbidden_employee_role(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """EMPLOYEE role should be forbidden from creating employees."""
        await _seed_employee(db_session, emp_id="EMP001", role=Role.EMPLOYEE)
        token = _make_token("EMP001", Role.EMPLOYEE)

        resp = await client.post(
            "/api/employees",
            json={
                "emp_id": "NEW002",
                "name": "Another Employee",
                "department": "Sales",
                "role": "EMPLOYEE",
                "password": "pass123",
                "shift_start_time": "09:00:00",
                "shift_end_time": "18:00:00",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/employees/{emp_id} — Get single employee
# ---------------------------------------------------------------------------
class TestGetEmployee:
    """GET /api/employees/{emp_id}"""

    async def test_get_employee_by_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Authenticated user should be able to get an employee by ID."""
        await _seed_employee(db_session, emp_id="EMP001", role=Role.EMPLOYEE)
        token = _make_token("EMP001", Role.EMPLOYEE)

        resp = await client.get(
            "/api/employees/EMP001",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["emp_id"] == "EMP001"
        assert data["name"] == "Test User"
        assert "hashed_password" not in data

    async def test_get_nonexistent_employee_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Requesting a non-existent employee should return 404."""
        await _seed_employee(db_session, emp_id="EMP001", role=Role.EMPLOYEE)
        token = _make_token("EMP001", Role.EMPLOYEE)

        resp = await client.get(
            "/api/employees/GHOST",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/employees — List employees
# ---------------------------------------------------------------------------
class TestListEmployees:
    """GET /api/employees"""

    async def test_list_employees_hr_sees_all(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """HR role should see all employees."""
        await _seed_employee(
            db_session, emp_id="HR001", name="HR Person", role=Role.HR
        )
        await _seed_employee(
            db_session, emp_id="EMP001", name="Employee One", role=Role.EMPLOYEE
        )
        await _seed_employee(
            db_session,
            emp_id="EMP002",
            name="Employee Two",
            department="Sales",
            role=Role.EMPLOYEE,
        )
        token = _make_token("HR001", Role.HR)

        resp = await client.get(
            "/api/employees",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3


# ---------------------------------------------------------------------------
# PUT /api/employees/{emp_id} — Update employee
# ---------------------------------------------------------------------------
class TestUpdateEmployee:
    """PUT /api/employees/{emp_id}"""

    async def test_update_employee_success_hr(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """HR role should be able to update another employee's info."""
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        await _seed_employee(db_session, emp_id="EMP001", role=Role.EMPLOYEE)
        token = _make_token("HR001", Role.HR)

        resp = await client.put(
            "/api/employees/EMP001",
            json={"name": "Updated Name", "department": "Marketing"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        assert data["department"] == "Marketing"

    async def test_update_own_profile_employee(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """EMPLOYEE should be able to update their own name."""
        await _seed_employee(db_session, emp_id="EMP001", role=Role.EMPLOYEE)
        token = _make_token("EMP001", Role.EMPLOYEE)

        resp = await client.put(
            "/api/employees/EMP001",
            json={"name": "My New Name"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My New Name"

    async def test_employee_cannot_change_role(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """EMPLOYEE should not be able to change roles (requires MANAGE_ROLES)."""
        await _seed_employee(db_session, emp_id="EMP001", role=Role.EMPLOYEE)
        token = _make_token("EMP001", Role.EMPLOYEE)

        resp = await client.put(
            "/api/employees/EMP001",
            json={"role": "ADMIN"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/employees/{emp_id} — Deactivate employee
# ---------------------------------------------------------------------------
class TestDeleteEmployee:
    """DELETE /api/employees/{emp_id}"""

    async def test_delete_employee_admin_only(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """ADMIN should be able to delete (deactivate) an employee."""
        await _seed_employee(db_session, emp_id="ADMIN01", role=Role.ADMIN)
        await _seed_employee(db_session, emp_id="EMP001", role=Role.EMPLOYEE)
        token = _make_token("ADMIN01", Role.ADMIN)

        resp = await client.delete(
            "/api/employees/EMP001",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify it's gone
        get_resp = await client.get(
            "/api/employees/EMP001",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------
class TestUnauthenticatedAccess:
    """Endpoints should return 401 without a valid token."""

    async def test_unauthenticated_list(self, client: AsyncClient):
        """GET /api/employees without token should return 401."""
        resp = await client.get("/api/employees")
        assert resp.status_code == 401

    async def test_unauthenticated_create(self, client: AsyncClient):
        """POST /api/employees without token should return 401."""
        resp = await client.post(
            "/api/employees",
            json={
                "emp_id": "X",
                "name": "X",
                "department": "X",
                "role": "EMPLOYEE",
                "password": "x",
                "shift_start_time": "09:00:00",
                "shift_end_time": "18:00:00",
            },
        )
        assert resp.status_code == 401
