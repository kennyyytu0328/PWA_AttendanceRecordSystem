"""Integration tests for workday calendar API endpoints.

TDD RED phase: tests written before the endpoint implementation.
"""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import settings
from app.utils.taiwan_calendar import DayInfo


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


def _make_raw_entries(year: int, month: int, count: int) -> list[dict]:
    """Create raw calendar entries for testing."""
    return [
        {
            "date": f"{year}{month:02d}{d:02d}",
            "week": "一",
            "isHoliday": False,
            "description": "",
        }
        for d in range(1, count + 1)
    ]


def _make_day_infos(year: int, month: int, count: int) -> list[DayInfo]:
    """Create DayInfo objects for testing."""
    return [
        DayInfo(
            date=datetime.date(year, month, d),
            weekday_zh="一",
            is_holiday=False,
            description="",
            is_makeup_workday=False,
        )
        for d in range(1, count + 1)
    ]


def _make_day_infos_year(year: int) -> list[DayInfo]:
    """Create DayInfo objects for an entire year."""
    import calendar as cal

    result: list[DayInfo] = []
    for m in range(1, 13):
        days_in_month = cal.monthrange(year, m)[1]
        for d in range(1, days_in_month + 1):
            result.append(
                DayInfo(
                    date=datetime.date(year, m, d),
                    weekday_zh="一",
                    is_holiday=False,
                    description="",
                    is_makeup_workday=False,
                )
            )
    return result


# ---------------------------------------------------------------------------
# GET /api/config/workdays
# ---------------------------------------------------------------------------
class TestGetWorkdays:
    """GET /api/config/workdays — any authenticated user."""

    async def test_get_workdays_returns_month_info(self, client: AsyncClient):
        """Should return day-by-day info for the requested month from cache."""
        cached_value = {"entries": _make_raw_entries(2026, 1, 31)}

        with patch(
            "app.repositories.system_config_repository.get_workday_calendar",
            new_callable=AsyncMock,
            return_value=cached_value,
        ):
            resp = await client.get(
                "/api/config/workdays",
                params={"year": 2026, "month": 1},
                headers=_auth_header("EMP001", "EMPLOYEE"),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["year"] == 2026
        assert data["month"] == 1
        assert len(data["days"]) == 31

    async def test_get_workdays_auto_fetches_when_not_cached(
        self, client: AsyncClient
    ):
        """Should auto-fetch from CDN when not cached, then return data."""
        cdn_data = _make_day_infos(2026, 1, 31)

        with (
            patch(
                "app.repositories.system_config_repository.get_workday_calendar",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.routers.system_config.fetch_calendar_from_cdn",
                new_callable=AsyncMock,
                return_value=cdn_data,
            ) as mock_fetch,
            patch(
                "app.repositories.system_config_repository.set_workday_calendar",
                new_callable=AsyncMock,
            ) as mock_set,
        ):
            resp = await client.get(
                "/api/config/workdays",
                params={"year": 2026, "month": 1},
                headers=_auth_header("EMP001", "EMPLOYEE"),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["days"]) == 31
        mock_fetch.assert_called_once_with(2026)
        mock_set.assert_called_once()

    async def test_get_workdays_unauthenticated(self, client: AsyncClient):
        """Should return 401 when no token is provided."""
        resp = await client.get(
            "/api/config/workdays",
            params={"year": 2026, "month": 1},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/config/workdays/refresh
# ---------------------------------------------------------------------------
class TestRefreshWorkdays:
    """POST /api/config/workdays/refresh — HR+ only."""

    async def test_refresh_workdays_hr_success(self, client: AsyncClient):
        """HR should be able to refresh calendar from CDN."""
        cdn_data = _make_day_infos_year(2026)

        with (
            patch(
                "app.routers.system_config.fetch_calendar_from_cdn",
                new_callable=AsyncMock,
                return_value=cdn_data,
            ),
            patch(
                "app.repositories.system_config_repository.set_workday_calendar",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post(
                "/api/config/workdays/refresh",
                params={"year": 2026},
                headers=_auth_header("HR001", "HR"),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["year"] == 2026
        assert data["count"] == 365
        assert data["message"] == "Calendar refreshed"

    async def test_refresh_workdays_employee_forbidden(self, client: AsyncClient):
        """EMPLOYEE should be forbidden from refreshing calendar."""
        resp = await client.post(
            "/api/config/workdays/refresh",
            params={"year": 2026},
            headers=_auth_header("EMP001", "EMPLOYEE"),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/config/workdays/status
# ---------------------------------------------------------------------------
class TestGetWorkdaysStatus:
    """GET /api/config/workdays/status — HR+ only."""

    async def test_get_workdays_status_hr(self, client: AsyncClient):
        """HR should be able to check calendar status."""
        resp = await client.get(
            "/api/config/workdays/status",
            headers=_auth_header("HR001", "HR"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "calendars" in data
        # Should check 3 years: current-1, current, current+1
        assert len(data["calendars"]) == 3

    async def test_get_workdays_status_employee_forbidden(self, client: AsyncClient):
        """EMPLOYEE should be forbidden from checking calendar status."""
        resp = await client.get(
            "/api/config/workdays/status",
            headers=_auth_header("EMP001", "EMPLOYEE"),
        )
        assert resp.status_code == 403
