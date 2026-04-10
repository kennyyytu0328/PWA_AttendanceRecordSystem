"""End-to-end workflow tests for the GoGoFresh Attendance System.

These tests exercise complete flows through the real API stack with a test
database (in-memory SQLite).  No service-layer mocking — the only mock used
is for geolocation in the punch flow, since GPS coordinates cannot be
generated programmatically.
"""

import datetime
from datetime import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary
from app.models.employee import Employee, Role
from app.services.geolocation_service import WorkModeResult
from app.utils.password import hash_password


# ---------------------------------------------------------------------------
# Helper: seed an employee in the DB and return a JWT token
# ---------------------------------------------------------------------------
async def _create_and_login(
    client: AsyncClient,
    db_session: AsyncSession,
    emp_id: str,
    role: Role,
    password: str = "testpass123",
    department: str = "Engineering",
) -> str:
    """Seed an employee directly in the DB, then login via the API.

    Returns the JWT access_token string.
    """
    emp = Employee(
        emp_id=emp_id,
        name=f"Test {role.value}",
        department=department,
        role=role,
        hashed_password=hash_password(password),
        shift_start_time=time(9, 0),
        shift_end_time=time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    resp = await client.post(
        "/api/auth/login",
        json={"emp_id": emp_id, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {emp_id}: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    """Return an Authorization header dict for convenience."""
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Full Onboarding Flow
# ---------------------------------------------------------------------------
class TestFullOnboardingFlow:
    """ADMIN creates HR, HR creates EMPLOYEE — all via the API."""

    async def test_onboarding_chain(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        # Step 1: Seed an ADMIN and login
        admin_token = await _create_and_login(
            client, db_session, "ADMIN001", Role.ADMIN
        )

        # Step 2: ADMIN creates an HR user via the API
        hr_payload = {
            "emp_id": "HR001",
            "name": "HR Person",
            "department": "Human Resources",
            "role": "HR",
            "password": "hrpass123",
            "shift_start_time": "09:00:00",
            "shift_end_time": "18:00:00",
        }
        create_hr_resp = await client.post(
            "/api/employees", json=hr_payload, headers=_auth(admin_token)
        )
        assert create_hr_resp.status_code == 201
        assert create_hr_resp.json()["emp_id"] == "HR001"
        assert create_hr_resp.json()["role"] == "HR"

        # Step 3: Login as the new HR user
        hr_login_resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "HR001", "password": "hrpass123"},
        )
        assert hr_login_resp.status_code == 200
        hr_token = hr_login_resp.json()["access_token"]

        # Step 4: HR creates a regular EMPLOYEE via the API
        emp_payload = {
            "emp_id": "EMP001",
            "name": "New Employee",
            "department": "Engineering",
            "role": "EMPLOYEE",
            "password": "emppass123",
            "shift_start_time": "09:00:00",
            "shift_end_time": "18:00:00",
        }
        create_emp_resp = await client.post(
            "/api/employees", json=emp_payload, headers=_auth(hr_token)
        )
        assert create_emp_resp.status_code == 201
        assert create_emp_resp.json()["emp_id"] == "EMP001"
        assert create_emp_resp.json()["role"] == "EMPLOYEE"

        # Step 5: Verify the employee exists by fetching via API
        get_resp = await client.get(
            "/api/employees/EMP001", headers=_auth(hr_token)
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "New Employee"
        assert get_resp.json()["department"] == "Engineering"

        # Step 6: The new employee can also login
        emp_login_resp = await client.post(
            "/api/auth/login",
            json={"emp_id": "EMP001", "password": "emppass123"},
        )
        assert emp_login_resp.status_code == 200
        emp_token = emp_login_resp.json()["access_token"]

        # Step 7: The employee can view their own identity
        me_resp = await client.get("/api/auth/me", headers=_auth(emp_token))
        assert me_resp.status_code == 200
        assert me_resp.json()["emp_id"] == "EMP001"
        assert me_resp.json()["role"] == "EMPLOYEE"


# ---------------------------------------------------------------------------
# 2. Full Punch Flow
# ---------------------------------------------------------------------------
class TestFullPunchFlow:
    """Employee punches in via GPS, verified through the API stack."""

    async def test_punch_and_verify_today(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        # Step 1: Seed an HR user to set office location
        hr_token = await _create_and_login(
            client, db_session, "HR001", Role.HR
        )

        # Step 2: Set office location via the config API
        office_location = {"latitude": 25.033, "longitude": 121.565}
        set_loc_resp = await client.put(
            "/api/config/office-location",
            json=office_location,
            headers=_auth(hr_token),
        )
        assert set_loc_resp.status_code == 200

        # Step 3: Seed an employee and login
        emp_token = await _create_and_login(
            client, db_session, "EMP001", Role.EMPLOYEE
        )

        # Step 4: Punch with GPS — mock the geolocation service to avoid
        # real haversine dependency on exact coordinate matching
        fake_geo_result = WorkModeResult(
            work_mode=WorkMode.OFFICE,
            distance_km=0.02,
            accuracy=10.0,
            is_low_accuracy=False,
        )

        with patch(
            "app.services.attendance_service.geolocation_service.determine_work_mode",
            new_callable=AsyncMock,
            return_value=fake_geo_result,
        ):
            punch_resp = await client.post(
                "/api/attendance/punch",
                json={
                    "latitude": 25.033,
                    "longitude": 121.565,
                    "accuracy": 10.0,
                },
                headers=_auth(emp_token),
            )

        assert punch_resp.status_code == 200
        punch_data = punch_resp.json()
        assert punch_data["work_mode"] == "OFFICE"
        assert punch_data["distance_km"] == 0.02
        assert punch_data["is_low_accuracy"] is False
        assert punch_data["log"]["emp_id"] == "EMP001"

        # Step 5: Verify today's logs contain the punch
        today_resp = await client.get(
            "/api/attendance/today", headers=_auth(emp_token)
        )
        assert today_resp.status_code == 200
        today_logs = today_resp.json()
        assert len(today_logs) >= 1
        assert today_logs[0]["emp_id"] == "EMP001"
        assert today_logs[0]["work_mode"] == "OFFICE"


# ---------------------------------------------------------------------------
# 3. Full Reporting Flow
# ---------------------------------------------------------------------------
class TestFullReportingFlow:
    """Seed attendance data, generate summaries, get reports and exports."""

    async def test_reporting_pipeline(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        today = datetime.date.today()

        # Step 1: Seed employees for different roles
        admin_token = await _create_and_login(
            client, db_session, "ADMIN001", Role.ADMIN
        )
        mgr_token = await _create_and_login(
            client, db_session, "MGR001", Role.MANAGER
        )
        hr_token = await _create_and_login(
            client, db_session, "HR001", Role.HR, department="Human Resources"
        )
        _emp_token = await _create_and_login(
            client, db_session, "EMP001", Role.EMPLOYEE
        )

        # Step 2: Seed attendance logs directly in the DB (avoids geolocation)
        now = datetime.datetime.now(datetime.UTC)
        clock_in_time = now.replace(hour=8, minute=55, second=0, microsecond=0)
        clock_out_time = now.replace(hour=18, minute=5, second=0, microsecond=0)

        log_in = AttendanceLog(
            emp_id="EMP001",
            timestamp=clock_in_time,
            latitude=25.033,
            longitude=121.565,
            accuracy=10.0,
            ip_address="127.0.0.1",
            work_mode=WorkMode.OFFICE,
            is_overridden=False,
        )
        log_out = AttendanceLog(
            emp_id="EMP001",
            timestamp=clock_out_time,
            latitude=25.033,
            longitude=121.565,
            accuracy=10.0,
            ip_address="127.0.0.1",
            work_mode=WorkMode.OFFICE,
            is_overridden=False,
        )
        db_session.add(log_in)
        db_session.add(log_out)
        await db_session.commit()

        # Step 3: ADMIN generates daily summaries
        gen_resp = await client.post(
            "/api/reports/generate",
            params={"date": today.isoformat()},
            headers=_auth(admin_token),
        )
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["generated_count"] >= 1
        assert gen_data["date"] == today.isoformat()

        # Step 4: MANAGER views the daily report
        daily_resp = await client.get(
            "/api/reports/daily",
            params={"start_date": today.isoformat(), "end_date": today.isoformat()},
            headers=_auth(mgr_token),
        )
        assert daily_resp.status_code == 200
        daily_data = daily_resp.json()
        assert len(daily_data) >= 1

        # Find the EMP001 summary
        emp_summary = next(
            (s for s in daily_data if s["emp_id"] == "EMP001"), None
        )
        assert emp_summary is not None
        assert emp_summary["status"] in [
            "NORMAL",
            "LATE",
            "EARLY_LEAVE",
            "ABNORMAL",
        ]

        # Step 5: HR exports as JSON
        json_export_resp = await client.get(
            "/api/reports/export",
            params={
                "format": "json",
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
            },
            headers=_auth(hr_token),
        )
        assert json_export_resp.status_code == 200
        json_data = json_export_resp.json()
        assert isinstance(json_data, list)
        assert len(json_data) >= 1
        # Phase 12: other users (ADMIN/HR/MANAGER) may now get ABSENT summaries
        # on workdays, so don't rely on sort order — find EMP001 specifically.
        assert any(row["emp_id"] == "EMP001" for row in json_data)

        # Step 6: HR exports as CSV
        csv_export_resp = await client.get(
            "/api/reports/export",
            params={
                "format": "csv",
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
            },
            headers=_auth(hr_token),
        )
        assert csv_export_resp.status_code == 200
        assert "text/csv" in csv_export_resp.headers.get("content-type", "")
        csv_text = csv_export_resp.text
        assert "emp_id" in csv_text  # header row
        assert "EMP001" in csv_text  # data row


# ---------------------------------------------------------------------------
# 4. Role-Based Access Flow
# ---------------------------------------------------------------------------
class TestRoleBasedAccessFlow:
    """Verify RBAC across all four role levels."""

    async def test_role_hierarchy_enforcement(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        # Seed users for each role
        emp_token = await _create_and_login(
            client, db_session, "EMP001", Role.EMPLOYEE
        )
        mgr_token = await _create_and_login(
            client, db_session, "MGR001", Role.MANAGER
        )
        hr_token = await _create_and_login(
            client, db_session, "HR001", Role.HR, department="Human Resources"
        )
        admin_token = await _create_and_login(
            client, db_session, "ADMIN001", Role.ADMIN
        )

        today = datetime.date.today().isoformat()

        # -- EMPLOYEE restrictions --

        # EMPLOYEE cannot create employees (requires HR+)
        create_resp = await client.post(
            "/api/employees",
            json={
                "emp_id": "NEW001",
                "name": "Blocked",
                "department": "Test",
                "role": "EMPLOYEE",
                "password": "pass123",
                "shift_start_time": "09:00:00",
                "shift_end_time": "18:00:00",
            },
            headers=_auth(emp_token),
        )
        assert create_resp.status_code == 403

        # EMPLOYEE cannot access team attendance (requires MANAGER+)
        team_resp = await client.get(
            "/api/attendance/team",
            params={"start_date": today, "end_date": today},
            headers=_auth(emp_token),
        )
        assert team_resp.status_code == 403

        # EMPLOYEE cannot access all attendance (requires HR+)
        all_resp = await client.get(
            "/api/attendance/all",
            params={"start_date": today, "end_date": today},
            headers=_auth(emp_token),
        )
        assert all_resp.status_code == 403

        # EMPLOYEE cannot access daily reports (requires MANAGER+)
        report_resp = await client.get(
            "/api/reports/daily",
            params={"start_date": today, "end_date": today},
            headers=_auth(emp_token),
        )
        assert report_resp.status_code == 403

        # EMPLOYEE cannot access exports (requires HR+)
        export_resp = await client.get(
            "/api/reports/export",
            params={
                "format": "json",
                "start_date": today,
                "end_date": today,
            },
            headers=_auth(emp_token),
        )
        assert export_resp.status_code == 403

        # EMPLOYEE cannot set office location (requires HR+)
        loc_resp = await client.put(
            "/api/config/office-location",
            json={"latitude": 0.0, "longitude": 0.0},
            headers=_auth(emp_token),
        )
        assert loc_resp.status_code == 403

        # EMPLOYEE cannot access generic config (requires ADMIN)
        config_resp = await client.get(
            "/api/config/some_key",
            headers=_auth(emp_token),
        )
        assert config_resp.status_code == 403

        # EMPLOYEE cannot generate summaries (requires ADMIN)
        gen_resp = await client.post(
            "/api/reports/generate",
            params={"date": today},
            headers=_auth(emp_token),
        )
        assert gen_resp.status_code == 403

        # EMPLOYEE cannot delete employees (requires ADMIN)
        del_resp = await client.delete(
            "/api/employees/MGR001",
            headers=_auth(emp_token),
        )
        assert del_resp.status_code == 403

        # -- MANAGER can access team but not "all" or HR-level endpoints --

        mgr_team_resp = await client.get(
            "/api/attendance/team",
            params={"start_date": today, "end_date": today},
            headers=_auth(mgr_token),
        )
        assert mgr_team_resp.status_code == 200

        mgr_daily_resp = await client.get(
            "/api/reports/daily",
            params={"start_date": today, "end_date": today},
            headers=_auth(mgr_token),
        )
        assert mgr_daily_resp.status_code == 200

        # MANAGER cannot access "all" attendance (requires HR+)
        mgr_all_resp = await client.get(
            "/api/attendance/all",
            params={"start_date": today, "end_date": today},
            headers=_auth(mgr_token),
        )
        assert mgr_all_resp.status_code == 403

        # MANAGER cannot export (requires HR+)
        mgr_export_resp = await client.get(
            "/api/reports/export",
            params={
                "format": "json",
                "start_date": today,
                "end_date": today,
            },
            headers=_auth(mgr_token),
        )
        assert mgr_export_resp.status_code == 403

        # MANAGER cannot set office location (requires HR+)
        mgr_loc_resp = await client.put(
            "/api/config/office-location",
            json={"latitude": 0.0, "longitude": 0.0},
            headers=_auth(mgr_token),
        )
        assert mgr_loc_resp.status_code == 403

        # MANAGER cannot access generic config (requires ADMIN)
        mgr_cfg_resp = await client.get(
            "/api/config/some_key",
            headers=_auth(mgr_token),
        )
        assert mgr_cfg_resp.status_code == 403

        # -- HR can access all attendance and exports --

        hr_all_resp = await client.get(
            "/api/attendance/all",
            params={"start_date": today, "end_date": today},
            headers=_auth(hr_token),
        )
        assert hr_all_resp.status_code == 200

        hr_export_resp = await client.get(
            "/api/reports/export",
            params={
                "format": "json",
                "start_date": today,
                "end_date": today,
            },
            headers=_auth(hr_token),
        )
        assert hr_export_resp.status_code == 200

        # HR can set office location
        hr_loc_resp = await client.put(
            "/api/config/office-location",
            json={"latitude": 25.0, "longitude": 121.0},
            headers=_auth(hr_token),
        )
        assert hr_loc_resp.status_code == 200

        # HR cannot access generic config (requires ADMIN)
        hr_cfg_resp = await client.get(
            "/api/config/some_key",
            headers=_auth(hr_token),
        )
        assert hr_cfg_resp.status_code == 403

        # HR cannot generate summaries (requires ADMIN)
        hr_gen_resp = await client.post(
            "/api/reports/generate",
            params={"date": today},
            headers=_auth(hr_token),
        )
        assert hr_gen_resp.status_code == 403

        # -- ADMIN can access everything --

        admin_cfg_resp = await client.get(
            "/api/config/some_key",
            headers=_auth(admin_token),
        )
        assert admin_cfg_resp.status_code == 200

        admin_gen_resp = await client.post(
            "/api/reports/generate",
            params={"date": today},
            headers=_auth(admin_token),
        )
        assert admin_gen_resp.status_code == 200

        admin_set_cfg_resp = await client.put(
            "/api/config/custom_setting",
            json={"value": {"enabled": True}},
            headers=_auth(admin_token),
        )
        assert admin_set_cfg_resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. Office Location Change Flow
# ---------------------------------------------------------------------------
class TestOfficeLocationChangeFlow:
    """HR sets and updates the office location via the API."""

    async def test_set_and_update_office_location(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        # Step 1: Seed HR user and login
        hr_token = await _create_and_login(
            client, db_session, "HR001", Role.HR, department="Human Resources"
        )

        # Step 2: Initially, office location should be unset (value is None)
        get_initial_resp = await client.get(
            "/api/config/office-location", headers=_auth(hr_token)
        )
        assert get_initial_resp.status_code == 200
        assert get_initial_resp.json()["key"] == "office_location"
        assert get_initial_resp.json()["value"] is None

        # Step 3: Set the initial office location
        first_location = {"latitude": 25.033, "longitude": 121.565}
        set_resp = await client.put(
            "/api/config/office-location",
            json=first_location,
            headers=_auth(hr_token),
        )
        assert set_resp.status_code == 200
        set_data = set_resp.json()
        assert set_data["key"] == "office_location"
        assert set_data["value"]["latitude"] == 25.033
        assert set_data["value"]["longitude"] == 121.565
        assert set_data["updated_by"] == "HR001"

        # Step 4: Verify it is returned correctly on GET
        get_resp = await client.get(
            "/api/config/office-location", headers=_auth(hr_token)
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["value"]["latitude"] == 25.033
        assert get_data["value"]["longitude"] == 121.565

        # Step 5: Update to a new location
        second_location = {"latitude": 35.6762, "longitude": 139.6503}
        update_resp = await client.put(
            "/api/config/office-location",
            json=second_location,
            headers=_auth(hr_token),
        )
        assert update_resp.status_code == 200
        update_data = update_resp.json()
        assert update_data["value"]["latitude"] == 35.6762
        assert update_data["value"]["longitude"] == 139.6503

        # Step 6: Verify the update is persisted
        get_updated_resp = await client.get(
            "/api/config/office-location", headers=_auth(hr_token)
        )
        assert get_updated_resp.status_code == 200
        updated_data = get_updated_resp.json()
        assert updated_data["value"]["latitude"] == 35.6762
        assert updated_data["value"]["longitude"] == 139.6503
        assert updated_data["updated_by"] == "HR001"
        assert updated_data["updated_at"] is not None

        # Step 7: A regular employee can READ the location but not SET it
        emp_token = await _create_and_login(
            client, db_session, "EMP001", Role.EMPLOYEE
        )

        emp_get_resp = await client.get(
            "/api/config/office-location", headers=_auth(emp_token)
        )
        assert emp_get_resp.status_code == 200
        assert emp_get_resp.json()["value"]["latitude"] == 35.6762

        emp_put_resp = await client.put(
            "/api/config/office-location",
            json={"latitude": 0.0, "longitude": 0.0},
            headers=_auth(emp_token),
        )
        assert emp_put_resp.status_code == 403
