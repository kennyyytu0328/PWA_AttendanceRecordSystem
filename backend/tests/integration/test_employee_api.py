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

    async def test_hr_cannot_create_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """HR can manage employees but must NOT mint an ADMIN account.

        The admin UI hides the ADMIN option from non-admins; this enforces the
        same rule at the API so a crafted POST can't bypass it (privilege
        escalation). Creating an ADMIN requires MANAGE_ROLES (ADMIN only).
        """
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        token = _make_token("HR001", Role.HR)

        resp = await client.post(
            "/api/employees",
            json={
                "emp_id": "EVIL01",
                "name": "Escalated Admin",
                "department": "Sales",
                "role": "ADMIN",
                "password": "newpass123",
                "shift_start_time": "09:00:00",
                "shift_end_time": "18:00:00",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403
        # The account must not have been created.
        get_resp = await client.get(
            "/api/employees/EVIL01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 404

    async def test_admin_can_create_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """ADMIN (has MANAGE_ROLES) may create another ADMIN."""
        await _seed_employee(db_session, emp_id="ADMIN01", role=Role.ADMIN)
        token = _make_token("ADMIN01", Role.ADMIN)

        resp = await client.post(
            "/api/employees",
            json={
                "emp_id": "ADMIN02",
                "name": "Second Admin",
                "department": "Sales",
                "role": "ADMIN",
                "password": "newpass123",
                "shift_start_time": "09:00:00",
                "shift_end_time": "18:00:00",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 201
        assert resp.json()["role"] == "ADMIN"

    async def test_hr_can_still_create_hr(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """The guard targets ADMIN only — HR creating HR/MANAGER stays allowed."""
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        token = _make_token("HR001", Role.HR)

        resp = await client.post(
            "/api/employees",
            json={
                "emp_id": "HR002",
                "name": "Another HR",
                "department": "Sales",
                "role": "HR",
                "password": "newpass123",
                "shift_start_time": "09:00:00",
                "shift_end_time": "18:00:00",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 201
        assert resp.json()["role"] == "HR"


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
        """ADMIN should be able to delete an employee with no attendance logs."""
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

    async def test_delete_employee_with_logs_blocked(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Hard delete must be refused when attendance_logs reference the employee.

        Uses ADMIN since DELETE is ADMIN-only (Task 10).
        """
        from app.models.attendance_log import AttendanceLog, WorkMode

        await _seed_employee(db_session, emp_id="ADMIN01", role=Role.ADMIN)
        await _seed_employee(db_session, emp_id="EMP002", role=Role.EMPLOYEE)
        db_session.add(
            AttendanceLog(
                emp_id="EMP002",
                timestamp=datetime.datetime.now(UTC),
                latitude=25.0,
                longitude=121.0,
                accuracy=10.0,
                ip_address="127.0.0.1",
                work_mode=WorkMode.OFFICE,
            )
        )
        await db_session.commit()

        token = _make_token("ADMIN01", Role.ADMIN)
        resp = await client.delete(
            "/api/employees/EMP002",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409
        assert "terminate" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/employees/{emp_id}/terminate — Soft-delete
# ---------------------------------------------------------------------------
class TestTerminateEmployee:
    """POST /api/employees/{emp_id}/terminate"""

    async def test_terminate_employee_hr(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """HR marks an employee as terminated; terminated_at is populated."""
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        await _seed_employee(db_session, emp_id="EMP001", role=Role.EMPLOYEE)
        token = _make_token("HR001", Role.HR)

        resp = await client.post(
            "/api/employees/EMP001/terminate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["terminated_at"] is not None

    async def test_terminate_self_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """HR cannot terminate their own account (prevents lockout)."""
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        token = _make_token("HR001", Role.HR)

        resp = await client.post(
            "/api/employees/HR001/terminate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400

    async def test_terminated_employee_login_blocked(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """After termination, password login must be refused with Invalid credentials."""
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        await _seed_employee(
            db_session, emp_id="EMP001", role=Role.EMPLOYEE, password="correct"
        )
        hr_token = _make_token("HR001", Role.HR)

        term_resp = await client.post(
            "/api/employees/EMP001/terminate",
            headers={"Authorization": f"Bearer {hr_token}"},
        )
        assert term_resp.status_code == 200

        # Login with correct password should still fail
        login_resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP001", "password": "correct"},
        )
        assert login_resp.status_code == 401

    async def test_reactivate_employee(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Reactivate clears terminated_at."""
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        await _seed_employee(
            db_session, emp_id="EMP001", role=Role.EMPLOYEE, password="correct"
        )
        token = _make_token("HR001", Role.HR)

        await client.post(
            "/api/employees/EMP001/terminate",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.post(
            "/api/employees/EMP001/reactivate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["terminated_at"] is None

        # Login should work again
        login_resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP001", "password": "correct"},
        )
        assert login_resp.status_code == 200

    async def test_terminated_employee_history_visible_in_reports(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """LSA compliance: terminated employee's existing summaries must
        remain queryable via /api/reports/daily?emp_id=...&include_terminated=true.
        Regression test for the bug where generate_all_summaries()
        excluded terminated employees and hid their historical summaries.
        """
        from app.models.attendance_log import AttendanceLog, WorkMode

        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        await _seed_employee(db_session, emp_id="QUIT01", role=Role.EMPLOYEE)

        # Give QUIT01 a punch today so a LATE/NORMAL summary exists
        today = datetime.datetime.now(UTC).replace(hour=11, minute=0, second=0, microsecond=0)
        db_session.add(
            AttendanceLog(
                emp_id="QUIT01",
                timestamp=today,
                latitude=25.0,
                longitude=121.0,
                accuracy=10.0,
                ip_address="127.0.0.1",
                work_mode=WorkMode.OFFICE,
            )
        )
        await db_session.commit()

        # Seed monthly submission so the default submission_filter="submitted"
        # in /api/reports/daily doesn't hide QUIT01's summary.
        from app.repositories import monthly_submission_repository

        await monthly_submission_repository.upsert(
            db_session,
            emp_id="QUIT01",
            year=today.year,
            month=today.month,
        )

        token = _make_token("HR001", Role.HR)

        # Terminate QUIT01 after the punch
        term_resp = await client.post(
            "/api/employees/QUIT01/terminate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert term_resp.status_code == 200

        # Query reports for today filtering by QUIT01 — must return the summary
        today_iso = today.date().isoformat()
        resp = await client.get(
            f"/api/reports/daily?start_date={today_iso}&end_date={today_iso}&emp_id=QUIT01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1, f"Expected 1 summary for terminated QUIT01, got {rows}"
        assert rows[0]["emp_id"] == "QUIT01"

    async def test_list_employees_excludes_terminated_by_default(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """GET /api/employees hides terminated unless ?include_terminated=true."""
        await _seed_employee(db_session, emp_id="HR001", role=Role.HR)
        await _seed_employee(db_session, emp_id="ACTIVE1", role=Role.EMPLOYEE)
        await _seed_employee(db_session, emp_id="QUIT1", role=Role.EMPLOYEE)
        token = _make_token("HR001", Role.HR)

        await client.post(
            "/api/employees/QUIT1/terminate",
            headers={"Authorization": f"Bearer {token}"},
        )

        resp = await client.get(
            "/api/employees",
            headers={"Authorization": f"Bearer {token}"},
        )
        ids = {emp["emp_id"] for emp in resp.json()}
        assert "ACTIVE1" in ids
        assert "QUIT1" not in ids
        assert "HR001" in ids

        resp2 = await client.get(
            "/api/employees?include_terminated=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        ids2 = {emp["emp_id"] for emp in resp2.json()}
        assert "QUIT1" in ids2


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
