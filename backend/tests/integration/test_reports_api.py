"""Integration tests for the reports router.

TDD RED phase: tests should FAIL because routers/reports.py doesn't exist yet.
Uses the shared conftest.py fixtures (client, db_session, setup_db).
Mocks reporting_service functions at the router level.
"""

import datetime
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import settings
from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary
from app.models.employee import Role


# ---------------------------------------------------------------------------
# Helper: create a JWT token for a given employee and role
# ---------------------------------------------------------------------------
def _make_token(emp_id: str, role: str) -> str:
    payload = {
        "sub": emp_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


# ---------------------------------------------------------------------------
# Helper: build a mock DailyAttendanceSummary
# ---------------------------------------------------------------------------
def _make_summary(
    emp_id: str = "EMP001",
    date: datetime.date = datetime.date(2026, 3, 18),
    status: AttendanceStatus = AttendanceStatus.NORMAL,
) -> DailyAttendanceSummary:
    return DailyAttendanceSummary(
        id=1,
        emp_id=emp_id,
        date=date,
        first_clock_in=datetime.datetime(2026, 3, 18, 8, 55, tzinfo=datetime.UTC),
        last_clock_out=datetime.datetime(2026, 3, 18, 18, 5, tzinfo=datetime.UTC),
        status=status,
    )


# ---------------------------------------------------------------------------
# GET /api/reports/daily
# ---------------------------------------------------------------------------
class TestGetDailyReport:
    """GET /api/reports/daily — requires MANAGER+ role."""

    async def test_daily_report_success_manager(self, client: AsyncClient):
        """MANAGER should be able to get a daily report."""
        token = _make_token("EMP010", Role.MANAGER.value)
        mock_summaries = [_make_summary()]

        with patch(
            "app.routers.reports.reporting_service.get_daily_report",
            new_callable=AsyncMock,
            return_value=mock_summaries,
        ) as mock_fn:
            resp = await client.get(
                "/api/reports/daily",
                params={"start_date": "2026-03-18", "end_date": "2026-03-18"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["emp_id"] == "EMP001"
        mock_fn.assert_awaited_once()

    async def test_daily_report_forbidden_employee(self, client: AsyncClient):
        """EMPLOYEE role should be forbidden from viewing daily reports."""
        token = _make_token("EMP001", Role.EMPLOYEE.value)

        resp = await client.get(
            "/api/reports/daily",
            params={"start_date": "2026-03-18", "end_date": "2026-03-18"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403

    async def test_daily_report_missing_date(self, client: AsyncClient):
        """Missing required 'date' param should return 422."""
        token = _make_token("EMP010", Role.MANAGER.value)

        resp = await client.get(
            "/api/reports/daily",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/reports/export
# ---------------------------------------------------------------------------
class TestExportReport:
    """GET /api/reports/export — requires HR+ role."""

    async def test_export_csv_success(self, client: AsyncClient):
        """HR should be able to export attendance as CSV."""
        token = _make_token("EMP020", Role.HR.value)
        csv_content = "emp_id,name,department,date,first_clock_in,last_clock_out,status\nEMP001,Test,Eng,2026-03-18,08:55,18:05,NORMAL\n"

        with patch(
            "app.routers.reports.reporting_service.export_attendance",
            new_callable=AsyncMock,
            return_value=csv_content,
        ) as mock_fn:
            resp = await client.get(
                "/api/reports/export",
                params={
                    "format": "csv",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-18",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "EMP001" in resp.text
        mock_fn.assert_awaited_once()

    async def test_export_json_success(self, client: AsyncClient):
        """HR should be able to export attendance as JSON."""
        token = _make_token("EMP020", Role.HR.value)
        json_content = json.dumps([
            {
                "emp_id": "EMP001",
                "name": "Test",
                "department": "Eng",
                "date": "2026-03-18",
                "first_clock_in": "08:55",
                "last_clock_out": "18:05",
                "status": "NORMAL",
            }
        ])

        with patch(
            "app.routers.reports.reporting_service.export_attendance",
            new_callable=AsyncMock,
            return_value=json_content,
        ) as mock_fn:
            resp = await client.get(
                "/api/reports/export",
                params={
                    "format": "json",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-18",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["emp_id"] == "EMP001"
        mock_fn.assert_awaited_once()

    async def test_export_forbidden_employee(self, client: AsyncClient):
        """EMPLOYEE role should be forbidden from exporting reports."""
        token = _make_token("EMP001", Role.EMPLOYEE.value)

        resp = await client.get(
            "/api/reports/export",
            params={
                "format": "csv",
                "start_date": "2026-03-01",
                "end_date": "2026-03-18",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403

    async def test_export_missing_required_params(self, client: AsyncClient):
        """Missing start_date and end_date should return 422."""
        token = _make_token("EMP020", Role.HR.value)

        resp = await client.get(
            "/api/reports/export",
            params={"format": "csv"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/reports/generate
# ---------------------------------------------------------------------------
class TestGenerateSummary:
    """POST /api/reports/generate — requires ADMIN role only."""

    async def test_generate_success_admin(self, client: AsyncClient):
        """ADMIN should be able to trigger daily summary generation."""
        token = _make_token("EMP099", Role.ADMIN.value)
        mock_summaries = [_make_summary(), _make_summary(emp_id="EMP002")]

        with patch(
            "app.routers.reports.reporting_service.generate_all_summaries",
            new_callable=AsyncMock,
            return_value=mock_summaries,
        ) as mock_fn:
            resp = await client.post(
                "/api/reports/generate",
                params={"date": "2026-03-18"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["generated_count"] == 2
        mock_fn.assert_awaited_once()

    async def test_generate_forbidden_manager(self, client: AsyncClient):
        """MANAGER role should be forbidden from generating summaries."""
        token = _make_token("EMP010", Role.MANAGER.value)

        resp = await client.post(
            "/api/reports/generate",
            params={"date": "2026-03-18"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403

    async def test_generate_forbidden_hr(self, client: AsyncClient):
        """HR role should be forbidden from generating summaries."""
        token = _make_token("EMP020", Role.HR.value)

        resp = await client.post(
            "/api/reports/generate",
            params={"date": "2026-03-18"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403
