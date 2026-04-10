# Phase 13B: Monthly Punch Override & Taiwan Workday Calendar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable employees to bulk-edit their monthly clock-in/clock-out times via a calendar table, integrated with Taiwan's official workday calendar for holiday/補班 awareness.

**Architecture:** Backend adds a Taiwan calendar utility (auto-fetched from GitHub CDN, cached in `system_config` table), three new workday config endpoints, and a bulk override endpoint. Frontend adds a full monthly calendar table page at `/dashboard/monthly-override` and a calendar status section on the admin page. TDD throughout.

**Tech Stack:** Python FastAPI, SQLAlchemy/SQLModel, httpx (for GitHub fetch), Next.js, React, TailwindCSS, next-intl, vitest

---

## File Map

### Backend — New Files

| File | Responsibility |
|------|---------------|
| `backend/app/utils/taiwan_calendar.py` | Parse calendar JSON, provide `is_workday()`, `get_month_info()`, auto-fetch from CDN |
| `backend/app/schemas/bulk_override.py` | `BulkOverrideEntry`, `BulkOverrideRequest`, `BulkOverrideResponse` Pydantic schemas |
| `backend/tests/unit/test_taiwan_calendar.py` | Unit tests for calendar utility |
| `backend/tests/unit/test_bulk_override_service.py` | Unit tests for bulk override logic |
| `backend/tests/integration/test_workday_api.py` | Integration tests for workday endpoints |
| `backend/tests/integration/test_bulk_override_api.py` | Integration tests for bulk override endpoint |

### Backend — Modified Files

| File | Changes |
|------|---------|
| `backend/app/repositories/system_config_repository.py` | Add `get_workday_calendar()`, `set_workday_calendar()` helpers |
| `backend/app/repositories/attendance_repository.py` | Add `mark_overridden_by_employee_and_date()` |
| `backend/app/services/attendance_service.py` | Add `bulk_override_punches()` |
| `backend/app/routers/system_config.py` | Add 3 workday endpoints (GET workdays, POST refresh, GET status) |
| `backend/app/routers/attendance.py` | Add `PUT /api/attendance/override-bulk` |
| `backend/app/main.py` | No changes needed — routers already registered |

### Frontend — New Files

| File | Responsibility |
|------|---------------|
| `frontend/src/app/dashboard/monthly-override/page.tsx` | Monthly calendar table page |
| `frontend/__tests__/unit/app/monthly-override.test.tsx` | Unit tests for monthly override page |

### Frontend — Modified Files

| File | Changes |
|------|---------|
| `frontend/src/app/dashboard/page.tsx` | Add "Monthly Punch Override" quick action card |
| `frontend/src/app/admin/page.tsx` | Add `CalendarStatusSection` component |
| `frontend/src/types/index.ts` | Add workday/override types |
| `frontend/src/messages/en.json` | Add i18n keys for override & calendar |
| `frontend/src/messages/zh.json` | Add i18n keys for override & calendar |

---

## Task 1: Taiwan Calendar Utility — Core Functions

**Files:**
- Create: `backend/app/utils/taiwan_calendar.py`
- Test: `backend/tests/unit/test_taiwan_calendar.py`

### Step 1: Write failing tests for calendar parsing

- [ ] Create `backend/tests/unit/test_taiwan_calendar.py`:

```python
"""Tests for Taiwan workday calendar utility."""

import datetime
from dataclasses import dataclass

import pytest

from app.utils.taiwan_calendar import DayInfo, parse_calendar_json, get_month_info_from_data, is_workday_from_data


# --- Test data ---

_SAMPLE_CALENDAR: list[dict] = [
    {"date": "20260101", "week": "四", "isHoliday": True, "description": "中華民國開國紀念日"},
    {"date": "20260102", "week": "五", "isHoliday": False, "description": ""},
    {"date": "20260103", "week": "六", "isHoliday": True, "description": ""},
    {"date": "20260104", "week": "日", "isHoliday": True, "description": ""},
    {"date": "20260105", "week": "一", "isHoliday": False, "description": ""},
    {"date": "20260131", "week": "六", "isHoliday": False, "description": "補行上班"},
]


class TestParsing:
    def test_parse_calendar_json_returns_list_of_day_info(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        assert len(result) == 6
        assert isinstance(result[0], DayInfo)

    def test_parse_holiday_entry(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        day = result[0]  # 2026-01-01
        assert day.date == datetime.date(2026, 1, 1)
        assert day.is_holiday is True
        assert day.description == "中華民國開國紀念日"
        assert day.weekday_zh == "四"

    def test_parse_workday_entry(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        day = result[1]  # 2026-01-02
        assert day.date == datetime.date(2026, 1, 2)
        assert day.is_holiday is False
        assert day.description == ""

    def test_parse_makeup_workday(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        day = result[5]  # 2026-01-31, 補行上班
        assert day.is_holiday is False
        assert day.is_makeup_workday is True
        assert day.description == "補行上班"

    def test_weekend_without_description_is_not_makeup(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        day = result[2]  # 2026-01-03, Saturday holiday
        assert day.is_holiday is True
        assert day.is_makeup_workday is False


class TestIsWorkday:
    def test_regular_workday(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        assert is_workday_from_data(data, datetime.date(2026, 1, 2)) is True

    def test_national_holiday(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        assert is_workday_from_data(data, datetime.date(2026, 1, 1)) is False

    def test_weekend_is_not_workday(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        assert is_workday_from_data(data, datetime.date(2026, 1, 3)) is False

    def test_makeup_workday_is_workday(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        assert is_workday_from_data(data, datetime.date(2026, 1, 31)) is True

    def test_date_not_in_data_weekday_fallback(self):
        """Dates not in calendar data fall back to Mon-Fri = workday."""
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        # 2026-03-02 is Monday, not in sample data
        assert is_workday_from_data(data, datetime.date(2026, 3, 2)) is True

    def test_date_not_in_data_weekend_fallback(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        # 2026-03-07 is Saturday, not in sample data
        assert is_workday_from_data(data, datetime.date(2026, 3, 7)) is False


class TestGetMonthInfo:
    def test_returns_all_days_in_month(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        result = get_month_info_from_data(data, 2026, 1)
        assert len(result) == 31  # January has 31 days

    def test_fills_missing_days_with_defaults(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        result = get_month_info_from_data(data, 2026, 1)
        # 2026-01-06 is Tuesday, not in sample → default workday
        day_06 = next(d for d in result if d.date == datetime.date(2026, 1, 6))
        assert day_06.is_holiday is False
        assert day_06.description == ""

    def test_february_leap_year(self):
        data = parse_calendar_json([])
        result = get_month_info_from_data(data, 2028, 2)
        assert len(result) == 29  # 2028 is leap year

    def test_february_non_leap_year(self):
        data = parse_calendar_json([])
        result = get_month_info_from_data(data, 2026, 2)
        assert len(result) == 28
```

- [ ] Run tests to verify they fail:

```bash
cd backend && python -m pytest tests/unit/test_taiwan_calendar.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.taiwan_calendar'`

### Step 2: Implement calendar utility

- [ ] Create `backend/app/utils/taiwan_calendar.py`:

```python
"""Taiwan workday calendar utility.

Parses calendar JSON from ruyut/TaiwanCalendar (sourced from 行政院人事行政總處).
Data URL: https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json
"""

from __future__ import annotations

import calendar
import datetime
from dataclasses import dataclass
from typing import Any

_MAKEUP_KEYWORDS = ("補行上班", "補班")
_WEEKDAY_ZH = ["一", "二", "三", "四", "五", "六", "日"]

CALENDAR_CDN_URL = "https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json"


@dataclass(frozen=True)
class DayInfo:
    """Information about a single calendar day."""

    date: datetime.date
    weekday_zh: str
    is_holiday: bool
    description: str
    is_makeup_workday: bool


def parse_calendar_json(raw_entries: list[dict[str, Any]]) -> list[DayInfo]:
    """Parse raw JSON entries into DayInfo objects."""
    result: list[DayInfo] = []
    for entry in raw_entries:
        date_str = entry["date"]
        d = datetime.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        is_holiday = bool(entry["isHoliday"])
        description = entry.get("description", "")
        is_makeup = not is_holiday and any(kw in description for kw in _MAKEUP_KEYWORDS)
        weekday_zh = entry.get("week", _WEEKDAY_ZH[d.weekday()])
        result.append(
            DayInfo(
                date=d,
                weekday_zh=weekday_zh,
                is_holiday=is_holiday,
                description=description,
                is_makeup_workday=is_makeup,
            )
        )
    return result


def is_workday_from_data(data: list[DayInfo], target: datetime.date) -> bool:
    """Check if a date is a workday using parsed calendar data.

    Falls back to Mon-Fri if date is not in the data.
    """
    for day in data:
        if day.date == target:
            return not day.is_holiday
    # Fallback: Mon(0)-Fri(4) = workday
    return target.weekday() < 5


def get_month_info_from_data(
    data: list[DayInfo], year: int, month: int
) -> list[DayInfo]:
    """Get DayInfo for every day in a month.

    Days missing from calendar data are filled with defaults
    (Mon-Fri = workday, Sat-Sun = holiday).
    """
    days_in_month = calendar.monthrange(year, month)[1]
    data_by_date = {day.date: day for day in data}

    result: list[DayInfo] = []
    for day_num in range(1, days_in_month + 1):
        d = datetime.date(year, month, day_num)
        if d in data_by_date:
            result.append(data_by_date[d])
        else:
            is_weekend = d.weekday() >= 5
            result.append(
                DayInfo(
                    date=d,
                    weekday_zh=_WEEKDAY_ZH[d.weekday()],
                    is_holiday=is_weekend,
                    description="",
                    is_makeup_workday=False,
                )
            )
    return result
```

### Step 3: Run tests to verify they pass

- [ ] Run:

```bash
cd backend && python -m pytest tests/unit/test_taiwan_calendar.py -v
```

Expected: All 13 tests PASS

### Step 4: Commit

- [ ] Commit:

```bash
git add backend/app/utils/taiwan_calendar.py backend/tests/unit/test_taiwan_calendar.py
git commit -m "feat: add Taiwan workday calendar utility with parsing and workday detection"
```

---

## Task 2: Calendar Auto-Fetch & System Config Storage

**Files:**
- Modify: `backend/app/repositories/system_config_repository.py`
- Modify: `backend/app/utils/taiwan_calendar.py` (add fetch function)
- Test: `backend/tests/unit/test_taiwan_calendar.py` (add fetch tests)

### Step 1: Write failing tests for fetch and config storage

- [ ] Add to `backend/tests/unit/test_taiwan_calendar.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock

from app.utils.taiwan_calendar import fetch_calendar_from_cdn
from app.repositories import system_config_repository


class TestFetchFromCDN:
    @pytest.mark.asyncio
    async def test_fetch_success_returns_parsed_data(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"date": "20260101", "week": "四", "isHoliday": True, "description": "開國紀念日"},
            {"date": "20260102", "week": "五", "isHoliday": False, "description": ""},
        ]

        with patch("app.utils.taiwan_calendar.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await fetch_calendar_from_cdn(2026)

        assert len(result) == 2
        assert result[0].date == datetime.date(2026, 1, 1)

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_empty_list(self):
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("app.utils.taiwan_calendar.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await fetch_calendar_from_cdn(2026)

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_network_error_returns_empty_list(self):
        with patch("app.utils.taiwan_calendar.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))
            mock_client_cls.return_value = mock_client

            result = await fetch_calendar_from_cdn(2026)

        assert result == []
```

- [ ] Run tests to verify they fail:

```bash
cd backend && python -m pytest tests/unit/test_taiwan_calendar.py::TestFetchFromCDN -v
```

Expected: FAIL — `ImportError: cannot import name 'fetch_calendar_from_cdn'`

### Step 2: Implement fetch function and config helpers

- [ ] Add to `backend/app/utils/taiwan_calendar.py` (at the top, add `import httpx` and the async function at the bottom):

```python
import httpx


async def fetch_calendar_from_cdn(year: int) -> list[DayInfo]:
    """Fetch Taiwan calendar data from ruyut/TaiwanCalendar CDN.

    Returns empty list on any failure (network, 404, parse error).
    """
    url = CALENDAR_CDN_URL.format(year=year)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        if response.status_code != 200:
            return []
        return parse_calendar_json(response.json())
    except Exception:
        return []
```

- [ ] Add helpers to `backend/app/repositories/system_config_repository.py`:

```python
async def get_workday_calendar(
    session: AsyncSession, year: int
) -> dict[str, Any] | None:
    """Get cached workday calendar for a year."""
    config = await get_by_key(session, f"workday_calendar_{year}")
    if config is None:
        return None
    return config.value


async def set_workday_calendar(
    session: AsyncSession,
    year: int,
    entries: list[dict[str, Any]],
    updated_by: str,
) -> SystemConfig:
    """Cache workday calendar data for a year."""
    return await set_config(
        session,
        key=f"workday_calendar_{year}",
        value={"entries": entries, "year": year},
        updated_by=updated_by,
    )
```

### Step 3: Run tests to verify they pass

- [ ] Run:

```bash
cd backend && python -m pytest tests/unit/test_taiwan_calendar.py -v
```

Expected: All 16 tests PASS

### Step 4: Add `httpx` to dependencies

- [ ] Add `httpx` to `backend/pyproject.toml` dependencies (it may already be there for testing — check first):

```bash
cd backend && grep httpx pyproject.toml
```

If not present, add `"httpx>=0.27.0"` to the `dependencies` list.

### Step 5: Commit

- [ ] Commit:

```bash
git add backend/app/utils/taiwan_calendar.py backend/app/repositories/system_config_repository.py backend/tests/unit/test_taiwan_calendar.py backend/pyproject.toml
git commit -m "feat: add Taiwan calendar CDN fetch and system_config storage helpers"
```

---

## Task 3: Workday API Endpoints

**Files:**
- Modify: `backend/app/routers/system_config.py`
- Test: `backend/tests/integration/test_workday_api.py`

### Step 1: Write failing integration tests

- [ ] Create `backend/tests/integration/test_workday_api.py`:

```python
"""Integration tests for workday calendar API endpoints."""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

from app.config import settings
from app.models.attendance_log import WorkMode
from app.models.employee import Role


def _make_token(emp_id: str, role: str) -> str:
    payload = {
        "sub": emp_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


_EMPLOYEE_TOKEN = _make_token("EMP001", "EMPLOYEE")
_HR_TOKEN = _make_token("HR001", "HR")
_ADMIN_TOKEN = _make_token("ADMIN001", "ADMIN")

_CONFIG_REPO = "app.repositories.system_config_repository"
_CALENDAR_UTIL = "app.utils.taiwan_calendar"

_SAMPLE_DAY_INFOS = [
    {
        "date": "2026-01-01",
        "weekday_zh": "四",
        "is_holiday": True,
        "description": "中華民國開國紀念日",
        "is_makeup_workday": False,
    },
    {
        "date": "2026-01-02",
        "weekday_zh": "五",
        "is_holiday": False,
        "description": "",
        "is_makeup_workday": False,
    },
]


@pytest.mark.asyncio
async def test_get_workdays_returns_month_info(client):
    """GET /api/config/workdays?year=2026&month=1 returns day-by-day info."""
    from app.utils.taiwan_calendar import DayInfo

    mock_days = [
        DayInfo(
            date=datetime.date(2026, 1, 1),
            weekday_zh="四",
            is_holiday=True,
            description="中華民國開國紀念日",
            is_makeup_workday=False,
        ),
        DayInfo(
            date=datetime.date(2026, 1, 2),
            weekday_zh="五",
            is_holiday=False,
            description="",
            is_makeup_workday=False,
        ),
    ]

    with patch(
        f"{_CONFIG_REPO}.get_workday_calendar",
        new_callable=AsyncMock,
        return_value={"entries": [
            {"date": "20260101", "week": "四", "isHoliday": True, "description": "中華民國開國紀念日"},
            {"date": "20260102", "week": "五", "isHoliday": False, "description": ""},
        ], "year": 2026},
    ):
        resp = await client.get(
            "/api/config/workdays?year=2026&month=1",
            headers={"Authorization": f"Bearer {_EMPLOYEE_TOKEN}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "days" in body
    assert len(body["days"]) == 31  # January


@pytest.mark.asyncio
async def test_get_workdays_auto_fetches_when_not_cached(client):
    """GET /api/config/workdays auto-fetches from CDN when not in cache."""
    from app.utils.taiwan_calendar import DayInfo

    mock_fetched = [
        DayInfo(
            date=datetime.date(2026, 1, 1),
            weekday_zh="四",
            is_holiday=True,
            description="開國紀念日",
            is_makeup_workday=False,
        ),
    ]

    with (
        patch(f"{_CONFIG_REPO}.get_workday_calendar", new_callable=AsyncMock, return_value=None),
        patch(f"{_CALENDAR_UTIL}.fetch_calendar_from_cdn", new_callable=AsyncMock, return_value=mock_fetched),
        patch(f"{_CONFIG_REPO}.set_workday_calendar", new_callable=AsyncMock),
    ):
        resp = await client.get(
            "/api/config/workdays?year=2026&month=1",
            headers={"Authorization": f"Bearer {_EMPLOYEE_TOKEN}"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_workdays_unauthenticated(client):
    resp = await client.get("/api/config/workdays?year=2026&month=1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_workdays_hr_success(client):
    """POST /api/config/workdays/refresh succeeds for HR."""
    from app.utils.taiwan_calendar import DayInfo

    mock_fetched = [
        DayInfo(
            date=datetime.date(2026, 1, 1),
            weekday_zh="四",
            is_holiday=True,
            description="開國紀念日",
            is_makeup_workday=False,
        ),
    ]

    with (
        patch(f"{_CALENDAR_UTIL}.fetch_calendar_from_cdn", new_callable=AsyncMock, return_value=mock_fetched),
        patch(f"{_CONFIG_REPO}.set_workday_calendar", new_callable=AsyncMock),
    ):
        resp = await client.post(
            "/api/config/workdays/refresh?year=2026",
            headers={"Authorization": f"Bearer {_HR_TOKEN}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert body["count"] == 1


@pytest.mark.asyncio
async def test_refresh_workdays_employee_forbidden(client):
    resp = await client.post(
        "/api/config/workdays/refresh?year=2026",
        headers={"Authorization": f"Bearer {_EMPLOYEE_TOKEN}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_workdays_status_hr(client):
    """GET /api/config/workdays/status returns loaded calendar years."""
    from app.models.system_config import SystemConfig

    mock_config = SystemConfig(
        key="workday_calendar_2026",
        value={"entries": [], "year": 2026},
        updated_by="HR001",
        updated_at=datetime.datetime(2026, 4, 10, 8, 0, 0),
    )

    with patch(f"{_CONFIG_REPO}.get_by_key", new_callable=AsyncMock, side_effect=lambda s, k: mock_config if k == "workday_calendar_2026" else None):
        resp = await client.get(
            "/api/config/workdays/status",
            headers={"Authorization": f"Bearer {_HR_TOKEN}"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_workdays_status_employee_forbidden(client):
    resp = await client.get(
        "/api/config/workdays/status",
        headers={"Authorization": f"Bearer {_EMPLOYEE_TOKEN}"},
    )
    assert resp.status_code == 403
```

- [ ] Run tests to verify they fail:

```bash
cd backend && python -m pytest tests/integration/test_workday_api.py -v
```

Expected: FAIL — routes not defined

### Step 2: Implement workday endpoints

- [ ] Add to `backend/app/routers/system_config.py` (add imports at top and endpoints at bottom):

Add imports:

```python
from app.utils.taiwan_calendar import (
    fetch_calendar_from_cdn,
    get_month_info_from_data,
    parse_calendar_json,
)
```

Add endpoints:

```python
@router.get("/workdays")
async def get_workdays(
    year: int,
    month: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get day-by-day workday info for a month. Auto-fetches from CDN if not cached."""
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Invalid month")

    cached = await system_config_repository.get_workday_calendar(session, year)
    if cached is not None:
        raw_entries = cached.get("entries", [])
        data = parse_calendar_json(raw_entries)
    else:
        data = await fetch_calendar_from_cdn(year)
        if data:
            raw_entries = [
                {
                    "date": d.date.strftime("%Y%m%d"),
                    "week": d.weekday_zh,
                    "isHoliday": d.is_holiday,
                    "description": d.description,
                }
                for d in data
            ]
            await system_config_repository.set_workday_calendar(
                session, year, raw_entries, updated_by=user["sub"]
            )

    month_info = get_month_info_from_data(data, year, month)
    return {
        "year": year,
        "month": month,
        "days": [
            {
                "date": str(d.date),
                "weekday_zh": d.weekday_zh,
                "is_holiday": d.is_holiday,
                "description": d.description,
                "is_makeup_workday": d.is_makeup_workday,
            }
            for d in month_info
        ],
    }


@router.post("/workdays/refresh")
async def refresh_workdays(
    year: int,
    user: dict = Depends(require_role(Role.HR)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Re-fetch workday calendar from CDN for a given year. HR+ only."""
    data = await fetch_calendar_from_cdn(year)
    raw_entries = [
        {
            "date": d.date.strftime("%Y%m%d"),
            "week": d.weekday_zh,
            "isHoliday": d.is_holiday,
            "description": d.description,
        }
        for d in data
    ]
    await system_config_repository.set_workday_calendar(
        session, year, raw_entries, updated_by=user["sub"]
    )
    return {"year": year, "count": len(data), "message": "Calendar refreshed"}


@router.get("/workdays/status")
async def get_workdays_status(
    user: dict = Depends(require_role(Role.HR)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get status of loaded workday calendars. HR+ only."""
    current_year = datetime.datetime.now(datetime.UTC).year
    years_to_check = range(current_year - 1, current_year + 2)
    calendars: list[dict[str, Any]] = []

    for y in years_to_check:
        config = await system_config_repository.get_by_key(
            session, f"workday_calendar_{y}"
        )
        if config is not None:
            entry_count = len(config.value.get("entries", [])) if config.value else 0
            calendars.append({
                "year": y,
                "loaded": True,
                "entry_count": entry_count,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None,
                "updated_by": config.updated_by,
            })
        else:
            calendars.append({"year": y, "loaded": False})

    return {"calendars": calendars}
```

Also add `import datetime` and `from typing import Any` to the imports if not already present.

### Step 3: Run tests to verify they pass

- [ ] Run:

```bash
cd backend && python -m pytest tests/integration/test_workday_api.py -v
```

Expected: All 7 tests PASS

### Step 4: Commit

- [ ] Commit:

```bash
git add backend/app/routers/system_config.py backend/tests/integration/test_workday_api.py
git commit -m "feat: add workday calendar API endpoints (GET/refresh/status)"
```

---

## Task 4: Bulk Override Schema & Repository Helper

**Files:**
- Create: `backend/app/schemas/bulk_override.py`
- Modify: `backend/app/repositories/attendance_repository.py`

### Step 1: Create bulk override schemas

- [ ] Create `backend/app/schemas/bulk_override.py`:

```python
"""Schemas for bulk punch override."""

from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BulkOverrideEntry(BaseModel):
    """A single day's override data."""

    date: datetime.date
    first_clock_in: Optional[datetime.time] = None
    last_clock_out: Optional[datetime.time] = None


class BulkOverrideRequest(BaseModel):
    """Request to bulk-override punches for a month."""

    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)
    emp_id: Optional[str] = None  # HR+ only; defaults to self
    entries: list[BulkOverrideEntry] = Field(..., min_length=1)


class BulkOverrideDayResult(BaseModel):
    """Result for a single day after override."""

    date: str
    first_clock_in: Optional[str] = None
    last_clock_out: Optional[str] = None
    status: Optional[str] = None


class BulkOverrideResponse(BaseModel):
    """Response after bulk override."""

    emp_id: str
    updated_count: int
    results: list[BulkOverrideDayResult]
```

### Step 2: Add repository helper for marking logs overridden

- [ ] Add to `backend/app/repositories/attendance_repository.py`:

```python
async def mark_overridden_by_employee_and_date(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
) -> int:
    """Mark all non-overridden logs for an employee on a date as overridden.

    Returns the count of updated rows. This is the ONE exception to immutability:
    we flip is_overridden=True on old entries, but never delete or modify content.
    """
    start = datetime.datetime.combine(date, datetime.time.min)
    end = datetime.datetime.combine(date, datetime.time.max)
    stmt = (
        update(AttendanceLog)
        .where(
            AttendanceLog.emp_id == emp_id,
            AttendanceLog.timestamp >= start,
            AttendanceLog.timestamp <= end,
            AttendanceLog.is_overridden == False,  # noqa: E712
        )
        .values(is_overridden=True)
    )
    result = await session.execute(stmt)
    return result.rowcount
```

Also add `from sqlalchemy import update` to the imports at the top of the file.

### Step 3: Commit

- [ ] Commit:

```bash
git add backend/app/schemas/bulk_override.py backend/app/repositories/attendance_repository.py
git commit -m "feat: add bulk override schemas and mark_overridden repository helper"
```

---

## Task 5: Bulk Override Service Logic

**Files:**
- Modify: `backend/app/services/attendance_service.py`
- Test: `backend/tests/unit/test_bulk_override_service.py`

### Step 1: Write failing tests

- [ ] Create `backend/tests/unit/test_bulk_override_service.py`:

```python
"""Tests for bulk punch override service logic."""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role

_SERVICE = "app.services.attendance_service"
_ATTENDANCE_REPO = "app.repositories.attendance_repository"
_SUMMARY_REPO = "app.repositories.summary_repository"
_REPORTING = "app.services.reporting_service"
_EMPLOYEE_REPO = "app.repositories.employee_repository"


def _make_employee(emp_id: str = "EMP100", role: Role = Role.EMPLOYEE) -> Employee:
    return Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=role,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )


@pytest.mark.asyncio
async def test_bulk_override_creates_new_logs(db_session: AsyncSession):
    """Bulk override creates new attendance log entries."""
    from app.services.attendance_service import bulk_override_punches

    employee = _make_employee()
    db_session.add(employee)
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(8, 55), "last_clock_out": datetime.time(18, 5)},
    ]

    with patch(f"{_REPORTING}.generate_daily_summary", new_callable=AsyncMock, return_value=None):
        result = await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )

    assert result["updated_count"] == 1
    assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_bulk_override_marks_old_logs_overridden(db_session: AsyncSession):
    """Existing logs should be marked as is_overridden=True."""
    from app.services.attendance_service import bulk_override_punches

    employee = _make_employee()
    db_session.add(employee)

    old_log = AttendanceLog(
        emp_id="EMP100",
        timestamp=datetime.datetime(2026, 4, 1, 9, 0, 0),
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="127.0.0.1",
        work_mode=WorkMode.OFFICE,
        is_overridden=False,
    )
    db_session.add(old_log)
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(8, 50), "last_clock_out": datetime.time(18, 10)},
    ]

    with patch(f"{_REPORTING}.generate_daily_summary", new_callable=AsyncMock, return_value=None):
        await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )

    await db_session.refresh(old_log)
    assert old_log.is_overridden is True


@pytest.mark.asyncio
async def test_bulk_override_recalculates_summaries(db_session: AsyncSession):
    """Summaries should be regenerated for overridden dates."""
    from app.services.attendance_service import bulk_override_punches

    employee = _make_employee()
    db_session.add(employee)
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(8, 55), "last_clock_out": datetime.time(18, 5)},
        {"date": datetime.date(2026, 4, 2), "first_clock_in": datetime.time(9, 0), "last_clock_out": datetime.time(18, 0)},
    ]

    mock_generate = AsyncMock(return_value=None)
    with patch(f"{_REPORTING}.generate_daily_summary", mock_generate):
        await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )

    assert mock_generate.call_count == 2


@pytest.mark.asyncio
async def test_bulk_override_employee_cannot_override_others(db_session: AsyncSession):
    """EMPLOYEE role cannot override another employee's punches."""
    from app.services.attendance_service import bulk_override_punches

    db_session.add(_make_employee("EMP100", Role.EMPLOYEE))
    db_session.add(_make_employee("EMP200", Role.EMPLOYEE))
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(9, 0), "last_clock_out": datetime.time(18, 0)},
    ]

    with pytest.raises(PermissionError, match="cannot override"):
        await bulk_override_punches(
            db_session,
            emp_id="EMP200",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )


@pytest.mark.asyncio
async def test_bulk_override_hr_can_override_others(db_session: AsyncSession):
    """HR role can override any employee's punches."""
    from app.services.attendance_service import bulk_override_punches

    db_session.add(_make_employee("EMP100", Role.EMPLOYEE))
    db_session.add(_make_employee("HR001", Role.HR))
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(9, 0), "last_clock_out": datetime.time(18, 0)},
    ]

    with patch(f"{_REPORTING}.generate_daily_summary", new_callable=AsyncMock, return_value=None):
        result = await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="HR001",
            requesting_user_role=Role.HR,
            entries=entries,
        )

    assert result["updated_count"] == 1


@pytest.mark.asyncio
async def test_bulk_override_employee_not_found(db_session: AsyncSession):
    """Raises ValueError if target employee not found."""
    from app.services.attendance_service import bulk_override_punches

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": datetime.time(9, 0), "last_clock_out": datetime.time(18, 0)},
    ]

    with pytest.raises(ValueError, match="not found"):
        await bulk_override_punches(
            db_session,
            emp_id="NONEXISTENT",
            requesting_user_id="NONEXISTENT",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )


@pytest.mark.asyncio
async def test_bulk_override_skip_entry_with_no_times(db_session: AsyncSession):
    """Entries with both clock_in and clock_out as None should be skipped."""
    from app.services.attendance_service import bulk_override_punches

    db_session.add(_make_employee())
    await db_session.commit()

    entries = [
        {"date": datetime.date(2026, 4, 1), "first_clock_in": None, "last_clock_out": None},
    ]

    with patch(f"{_REPORTING}.generate_daily_summary", new_callable=AsyncMock, return_value=None):
        result = await bulk_override_punches(
            db_session,
            emp_id="EMP100",
            requesting_user_id="EMP100",
            requesting_user_role=Role.EMPLOYEE,
            entries=entries,
        )

    assert result["updated_count"] == 0
```

- [ ] Run tests to verify they fail:

```bash
cd backend && python -m pytest tests/unit/test_bulk_override_service.py -v
```

Expected: FAIL — `ImportError: cannot import name 'bulk_override_punches'`

### Step 2: Implement bulk_override_punches

- [ ] Add to `backend/app/services/attendance_service.py`:

Add import at top:

```python
from app.services import reporting_service
```

Add function:

```python
async def bulk_override_punches(
    session: AsyncSession,
    emp_id: str,
    requesting_user_id: str,
    requesting_user_role: Role,
    entries: list[dict],
) -> dict:
    """Bulk override attendance punches for an employee.

    Creates new log entries with is_overridden=True on old entries.
    Recalculates daily summaries for all affected dates.

    Raises:
        ValueError: If target employee not found.
        PermissionError: If requesting user lacks permission.
    """
    # Permission check
    if emp_id != requesting_user_id:
        role_index = [Role.EMPLOYEE, Role.MANAGER, Role.HR, Role.ADMIN].index(requesting_user_role)
        hr_index = [Role.EMPLOYEE, Role.MANAGER, Role.HR, Role.ADMIN].index(Role.HR)
        if role_index < hr_index:
            raise PermissionError("You cannot override another employee's punches")

    # Verify employee exists
    employee = await employee_repository.find_by_id(session, emp_id)
    if employee is None:
        raise ValueError(f"Employee {emp_id} not found")

    results: list[dict] = []
    updated_count = 0

    for entry in entries:
        entry_date = entry["date"]
        clock_in_time = entry.get("first_clock_in")
        clock_out_time = entry.get("last_clock_out")

        if clock_in_time is None and clock_out_time is None:
            continue

        # Mark existing logs as overridden
        await attendance_repository.mark_overridden_by_employee_and_date(
            session, emp_id, entry_date
        )

        # Create new clock-in log
        if clock_in_time is not None:
            clock_in_dt = datetime.datetime.combine(entry_date, clock_in_time)
            clock_in_log = AttendanceLog(
                emp_id=emp_id,
                timestamp=clock_in_dt,
                latitude=0.0,
                longitude=0.0,
                accuracy=0.0,
                ip_address="override",
                work_mode=WorkMode.OFFICE,
                is_overridden=False,
            )
            await attendance_repository.create_log(session, clock_in_log)

        # Create new clock-out log
        if clock_out_time is not None:
            clock_out_dt = datetime.datetime.combine(entry_date, clock_out_time)
            clock_out_log = AttendanceLog(
                emp_id=emp_id,
                timestamp=clock_out_dt,
                latitude=0.0,
                longitude=0.0,
                accuracy=0.0,
                ip_address="override",
                work_mode=WorkMode.OFFICE,
                is_overridden=False,
            )
            await attendance_repository.create_log(session, clock_out_log)

        # Recalculate summary
        summary = await reporting_service.generate_daily_summary(
            session, emp_id, entry_date
        )

        results.append({
            "date": str(entry_date),
            "first_clock_in": str(clock_in_time) if clock_in_time else None,
            "last_clock_out": str(clock_out_time) if clock_out_time else None,
            "status": summary.status.value if summary else None,
        })
        updated_count += 1

    await session.commit()

    return {
        "emp_id": emp_id,
        "updated_count": updated_count,
        "results": results,
    }
```

### Step 3: Run tests to verify they pass

- [ ] Run:

```bash
cd backend && python -m pytest tests/unit/test_bulk_override_service.py -v
```

Expected: All 7 tests PASS

### Step 4: Commit

- [ ] Commit:

```bash
git add backend/app/services/attendance_service.py backend/tests/unit/test_bulk_override_service.py
git commit -m "feat: add bulk_override_punches service with permission checks and summary recalculation"
```

---

## Task 6: Bulk Override API Endpoint

**Files:**
- Modify: `backend/app/routers/attendance.py`
- Test: `backend/tests/integration/test_bulk_override_api.py`

### Step 1: Write failing integration tests

- [ ] Create `backend/tests/integration/test_bulk_override_api.py`:

```python
"""Integration tests for bulk override API endpoint."""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

from app.config import settings
from app.models.employee import Role

_SERVICE = "app.services.attendance_service"


def _make_token(emp_id: str, role: str) -> str:
    payload = {
        "sub": emp_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@pytest.mark.asyncio
async def test_bulk_override_success(client):
    token = _make_token("EMP001", "EMPLOYEE")
    mock_result = {
        "emp_id": "EMP001",
        "updated_count": 1,
        "results": [{"date": "2026-04-01", "first_clock_in": "08:55:00", "last_clock_out": "18:05:00", "status": "NORMAL"}],
    }

    with patch(f"{_SERVICE}.bulk_override_punches", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.put(
            "/api/attendance/override-bulk",
            json={
                "year": 2026,
                "month": 4,
                "entries": [{"date": "2026-04-01", "first_clock_in": "08:55:00", "last_clock_out": "18:05:00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_count"] == 1


@pytest.mark.asyncio
async def test_bulk_override_hr_for_other_employee(client):
    token = _make_token("HR001", "HR")
    mock_result = {
        "emp_id": "EMP001",
        "updated_count": 1,
        "results": [{"date": "2026-04-01", "first_clock_in": "09:00:00", "last_clock_out": "18:00:00", "status": "NORMAL"}],
    }

    with patch(f"{_SERVICE}.bulk_override_punches", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.put(
            "/api/attendance/override-bulk",
            json={
                "year": 2026,
                "month": 4,
                "emp_id": "EMP001",
                "entries": [{"date": "2026-04-01", "first_clock_in": "09:00:00", "last_clock_out": "18:00:00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_bulk_override_unauthenticated(client):
    resp = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026,
            "month": 4,
            "entries": [{"date": "2026-04-01", "first_clock_in": "09:00:00", "last_clock_out": "18:00:00"}],
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bulk_override_empty_entries(client):
    token = _make_token("EMP001", "EMPLOYEE")
    resp = await client.put(
        "/api/attendance/override-bulk",
        json={"year": 2026, "month": 4, "entries": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422  # Validation error: min_length=1


@pytest.mark.asyncio
async def test_bulk_override_permission_error(client):
    token = _make_token("EMP001", "EMPLOYEE")

    with patch(
        f"{_SERVICE}.bulk_override_punches",
        new_callable=AsyncMock,
        side_effect=PermissionError("You cannot override another employee's punches"),
    ):
        resp = await client.put(
            "/api/attendance/override-bulk",
            json={
                "year": 2026,
                "month": 4,
                "emp_id": "EMP002",
                "entries": [{"date": "2026-04-01", "first_clock_in": "09:00:00", "last_clock_out": "18:00:00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 403
```

- [ ] Run tests to verify they fail:

```bash
cd backend && python -m pytest tests/integration/test_bulk_override_api.py -v
```

Expected: FAIL — route not defined

### Step 2: Implement the endpoint

- [ ] Add to `backend/app/routers/attendance.py`:

Add import at top:

```python
from app.schemas.bulk_override import BulkOverrideRequest
```

Add endpoint:

```python
@router.put("/override-bulk")
async def bulk_override(
    body: BulkOverrideRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Bulk override attendance punches for a month."""
    target_emp_id = body.emp_id if body.emp_id else user["sub"]
    try:
        result = await attendance_service.bulk_override_punches(
            session,
            emp_id=target_emp_id,
            requesting_user_id=user["sub"],
            requesting_user_role=Role(user["role"]),
            entries=[
                {
                    "date": entry.date,
                    "first_clock_in": entry.first_clock_in,
                    "last_clock_out": entry.last_clock_out,
                }
                for entry in body.entries
            ],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result
```

### Step 3: Run tests to verify they pass

- [ ] Run:

```bash
cd backend && python -m pytest tests/integration/test_bulk_override_api.py -v
```

Expected: All 5 tests PASS

### Step 4: Run all backend tests

- [ ] Verify no regressions:

```bash
cd backend && python -m pytest -v
```

Expected: All tests PASS

### Step 5: Commit

- [ ] Commit:

```bash
git add backend/app/routers/attendance.py backend/app/schemas/bulk_override.py backend/tests/integration/test_bulk_override_api.py
git commit -m "feat: add PUT /api/attendance/override-bulk endpoint"
```

---

## Task 7: Frontend Types & i18n

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/messages/en.json`
- Modify: `frontend/src/messages/zh.json`

### Step 1: Add TypeScript types

- [ ] Add to `frontend/src/types/index.ts`:

```typescript
export interface WorkdayInfo {
  readonly date: string;
  readonly weekday_zh: string;
  readonly is_holiday: boolean;
  readonly description: string;
  readonly is_makeup_workday: boolean;
}

export interface WorkdaysResponse {
  readonly year: number;
  readonly month: number;
  readonly days: readonly WorkdayInfo[];
}

export interface BulkOverrideEntry {
  readonly date: string;
  readonly first_clock_in: string | null;
  readonly last_clock_out: string | null;
}

export interface BulkOverrideRequest {
  readonly year: number;
  readonly month: number;
  readonly emp_id?: string;
  readonly entries: readonly BulkOverrideEntry[];
}

export interface BulkOverrideDayResult {
  readonly date: string;
  readonly first_clock_in: string | null;
  readonly last_clock_out: string | null;
  readonly status: string | null;
}

export interface BulkOverrideResponse {
  readonly emp_id: string;
  readonly updated_count: number;
  readonly results: readonly BulkOverrideDayResult[];
}

export interface CalendarStatus {
  readonly year: number;
  readonly loaded: boolean;
  readonly entry_count?: number;
  readonly updated_at?: string;
  readonly updated_by?: string;
}

export interface CalendarStatusResponse {
  readonly calendars: readonly CalendarStatus[];
}
```

### Step 2: Add i18n keys to en.json

- [ ] Add to `frontend/src/messages/en.json` (inside the root object):

```json
"monthlyOverride": {
  "title": "Monthly Punch Override",
  "subtitle": "Edit clock-in and clock-out times for each workday",
  "month": "Month",
  "year": "Year",
  "date": "Date",
  "day": "Day",
  "type": "Type",
  "clockIn": "Clock-in",
  "clockOut": "Clock-out",
  "status": "Status",
  "workday": "Workday",
  "holiday": "Holiday",
  "weekend": "Weekend",
  "makeupWorkday": "Make-up",
  "save": "Save All",
  "saving": "Saving...",
  "saveSuccess": "Punch overrides saved successfully. {count} days updated.",
  "saveError": "Failed to save overrides. Please try again.",
  "noChanges": "No changes to save.",
  "selectEmployee": "Select Employee",
  "allEmployees": "All Employees",
  "previousMonth": "Previous Month",
  "nextMonth": "Next Month"
},
"calendarStatus": {
  "title": "Workday Calendar Status",
  "year": "Year",
  "status": "Status",
  "loaded": "Loaded",
  "notLoaded": "Not Loaded",
  "entries": "entries",
  "lastUpdated": "Last Updated",
  "updatedBy": "Updated By",
  "refresh": "Update Full Year Calendar",
  "refreshing": "Updating...",
  "refreshSuccess": "Calendar refreshed successfully. {count} days loaded.",
  "refreshError": "Failed to refresh calendar."
}
```

### Step 3: Add i18n keys to zh.json

- [ ] Add to `frontend/src/messages/zh.json` (inside the root object):

```json
"monthlyOverride": {
  "title": "月度打卡修改",
  "subtitle": "編輯每個工作日的上班與下班時間",
  "month": "月份",
  "year": "年份",
  "date": "日期",
  "day": "星期",
  "type": "類型",
  "clockIn": "上班",
  "clockOut": "下班",
  "status": "狀態",
  "workday": "工作日",
  "holiday": "假日",
  "weekend": "週末",
  "makeupWorkday": "補班",
  "save": "儲存全部",
  "saving": "儲存中...",
  "saveSuccess": "打卡修改已儲存成功，共更新 {count} 天。",
  "saveError": "儲存失敗，請重試。",
  "noChanges": "沒有變更需要儲存。",
  "selectEmployee": "選擇員工",
  "allEmployees": "全部員工",
  "previousMonth": "上個月",
  "nextMonth": "下個月"
},
"calendarStatus": {
  "title": "工作日行事曆狀態",
  "year": "年份",
  "status": "狀態",
  "loaded": "已載入",
  "notLoaded": "未載入",
  "entries": "筆",
  "lastUpdated": "最後更新",
  "updatedBy": "更新者",
  "refresh": "更新全年行事曆",
  "refreshing": "更新中...",
  "refreshSuccess": "行事曆更新成功，共載入 {count} 天。",
  "refreshError": "行事曆更新失敗。"
}
```

### Step 4: Commit

- [ ] Commit:

```bash
git add frontend/src/types/index.ts frontend/src/messages/en.json frontend/src/messages/zh.json
git commit -m "feat: add frontend types and i18n keys for monthly override and calendar status"
```

---

## Task 8: Monthly Override Page

**Files:**
- Create: `frontend/src/app/dashboard/monthly-override/page.tsx`
- Test: `frontend/__tests__/unit/app/monthly-override.test.tsx`

### Step 1: Write failing tests

- [ ] Create `frontend/__tests__/unit/app/monthly-override.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock next-intl
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    const translations: Record<string, string> = {
      "monthlyOverride.title": "Monthly Punch Override",
      "monthlyOverride.subtitle": "Edit clock-in and clock-out times for each workday",
      "monthlyOverride.date": "Date",
      "monthlyOverride.day": "Day",
      "monthlyOverride.type": "Type",
      "monthlyOverride.clockIn": "Clock-in",
      "monthlyOverride.clockOut": "Clock-out",
      "monthlyOverride.status": "Status",
      "monthlyOverride.workday": "Workday",
      "monthlyOverride.holiday": "Holiday",
      "monthlyOverride.weekend": "Weekend",
      "monthlyOverride.makeupWorkday": "Make-up",
      "monthlyOverride.save": "Save All",
      "monthlyOverride.saving": "Saving...",
      "monthlyOverride.saveSuccess": `Punch overrides saved successfully. ${params?.count ?? 0} days updated.`,
      "monthlyOverride.noChanges": "No changes to save.",
      "monthlyOverride.selectEmployee": "Select Employee",
      "monthlyOverride.previousMonth": "Previous Month",
      "monthlyOverride.nextMonth": "Next Month",
      "common.backToDashboard": "Dashboard",
      "common.loading": "Loading...",
    };
    return translations[key] ?? key;
  },
}));

// Mock auth context
const mockUser = { emp_id: "EMP001", role: "EMPLOYEE" as const };
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: mockUser, isAuthenticated: true, isLoading: false }),
}));

// Mock API client
const mockGet = vi.fn();
const mockPut = vi.fn();
vi.mock("@/lib/api", () => ({
  apiClient: { get: (...args: unknown[]) => mockGet(...args), put: (...args: unknown[]) => mockPut(...args) },
  ApiError: class extends Error { status: number; constructor(s: number, m: string) { super(m); this.status = s; } },
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import MonthlyOverridePage from "@/app/dashboard/monthly-override/page";

const _MOCK_WORKDAYS = {
  year: 2026,
  month: 4,
  days: [
    { date: "2026-04-01", weekday_zh: "三", is_holiday: false, description: "", is_makeup_workday: false },
    { date: "2026-04-02", weekday_zh: "四", is_holiday: false, description: "", is_makeup_workday: false },
    { date: "2026-04-03", weekday_zh: "五", is_holiday: true, description: "清明節", is_makeup_workday: false },
    { date: "2026-04-04", weekday_zh: "六", is_holiday: true, description: "", is_makeup_workday: false },
    { date: "2026-04-05", weekday_zh: "日", is_holiday: true, description: "", is_makeup_workday: false },
  ],
};

const _MOCK_SUMMARIES: unknown[] = [];

describe("MonthlyOverridePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/api/config/workdays")) return Promise.resolve(_MOCK_WORKDAYS);
      if (url.includes("/api/attendance/summaries")) return Promise.resolve(_MOCK_SUMMARIES);
      return Promise.resolve([]);
    });
  });

  it("renders page title", async () => {
    render(<MonthlyOverridePage />);
    await waitFor(() => {
      expect(screen.getByText("Monthly Punch Override")).toBeTruthy();
    });
  });

  it("displays calendar table with workday rows", async () => {
    render(<MonthlyOverridePage />);
    await waitFor(() => {
      expect(screen.getByText("2026-04-01")).toBeTruthy();
      expect(screen.getByText("2026-04-02")).toBeTruthy();
    });
  });

  it("marks holidays as non-editable", async () => {
    render(<MonthlyOverridePage />);
    await waitFor(() => {
      expect(screen.getByText("清明節")).toBeTruthy();
    });
  });

  it("renders Save All button", async () => {
    render(<MonthlyOverridePage />);
    await waitFor(() => {
      expect(screen.getByText("Save All")).toBeTruthy();
    });
  });

  it("does not render employee selector for EMPLOYEE role", async () => {
    render(<MonthlyOverridePage />);
    await waitFor(() => {
      expect(screen.queryByText("Select Employee")).toBeNull();
    });
  });

  it("renders employee selector for HR role", async () => {
    mockUser.role = "HR" as const;
    render(<MonthlyOverridePage />);
    await waitFor(() => {
      expect(screen.getByText("Select Employee")).toBeTruthy();
    });
    mockUser.role = "EMPLOYEE" as const; // reset
  });

  it("shows success message after save", async () => {
    mockPut.mockResolvedValue({ emp_id: "EMP001", updated_count: 2, results: [] });
    render(<MonthlyOverridePage />);

    await waitFor(() => {
      expect(screen.getByText("Save All")).toBeTruthy();
    });

    // Simulate editing a time input (set clock-in for first workday)
    const clockInInputs = screen.getAllByTestId("clock-in-input");
    fireEvent.change(clockInInputs[0], { target: { value: "08:55" } });

    fireEvent.click(screen.getByText("Save All"));

    await waitFor(() => {
      expect(screen.getByText(/saved successfully/)).toBeTruthy();
    });
  });
});
```

- [ ] Run tests to verify they fail:

```bash
cd frontend && npx vitest run __tests__/unit/app/monthly-override.test.tsx
```

Expected: FAIL — module not found

### Step 2: Implement the monthly override page

- [ ] Create `frontend/src/app/dashboard/monthly-override/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, ChevronLeft, ChevronRight, Save } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { apiClient } from "@/lib/api";
import type {
  WorkdaysResponse,
  WorkdayInfo,
  DailyAttendanceSummary,
  BulkOverrideResponse,
  Employee,
} from "@/types";

const HR_ROLES = ["HR", "ADMIN"] as const;

function isHrOrAbove(role: string): boolean {
  return (HR_ROLES as readonly string[]).includes(role);
}

interface RowState {
  readonly clockIn: string;
  readonly clockOut: string;
  readonly originalClockIn: string;
  readonly originalClockOut: string;
}

export default function MonthlyOverridePage() {
  const { user } = useAuth();
  const t = useTranslations();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [days, setDays] = useState<readonly WorkdayInfo[]>([]);
  const [rows, setRows] = useState<Record<string, RowState>>({});
  const [summaries, setSummaries] = useState<readonly DailyAttendanceSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const [employees, setEmployees] = useState<readonly Employee[]>([]);
  const [selectedEmpId, setSelectedEmpId] = useState<string | null>(null);

  const role = user?.role ?? "EMPLOYEE";
  const targetEmpId = selectedEmpId ?? user?.emp_id ?? "";
  const canSelectEmployee = isHrOrAbove(role);

  const fetchData = useCallback(
    async (y: number, m: number, empId: string) => {
      setIsLoading(true);
      setMessage(null);
      try {
        const startDate = `${y}-${String(m).padStart(2, "0")}-01`;
        const lastDay = new Date(y, m, 0).getDate();
        const endDate = `${y}-${String(m).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;

        const [workdays, sums] = await Promise.all([
          apiClient.get<WorkdaysResponse>(`/api/config/workdays?year=${y}&month=${m}`),
          apiClient.get<DailyAttendanceSummary[]>(
            `/api/attendance/summaries?start_date=${startDate}&end_date=${endDate}${canSelectEmployee && empId !== user?.emp_id ? `&emp_id=${empId}` : ""}`
          ).catch(() => [] as DailyAttendanceSummary[]),
        ]);

        setDays(workdays.days);
        setSummaries(sums);

        const summaryByDate: Record<string, DailyAttendanceSummary> = {};
        for (const s of sums) {
          summaryByDate[s.date] = s;
        }

        const newRows: Record<string, RowState> = {};
        for (const day of workdays.days) {
          const summary = summaryByDate[day.date];
          const clockIn = summary?.first_clock_in
            ? summary.first_clock_in.substring(11, 16)
            : "";
          const clockOut = summary?.last_clock_out
            ? summary.last_clock_out.substring(11, 16)
            : "";
          newRows[day.date] = {
            clockIn,
            clockOut,
            originalClockIn: clockIn,
            originalClockOut: clockOut,
          };
        }
        setRows(newRows);
      } catch {
        setMessage({ type: "error", text: t("monthlyOverride.saveError") });
      } finally {
        setIsLoading(false);
      }
    },
    [canSelectEmployee, user?.emp_id, t],
  );

  useEffect(() => {
    if (user) {
      fetchData(year, month, targetEmpId);
    }
  }, [year, month, targetEmpId, user, fetchData]);

  useEffect(() => {
    if (canSelectEmployee) {
      apiClient.get<Employee[]>("/api/employees").then(setEmployees).catch(() => {});
    }
  }, [canSelectEmployee]);

  const handleTimeChange = (date: string, field: "clockIn" | "clockOut", value: string) => {
    setRows((prev) => ({
      ...prev,
      [date]: { ...prev[date], [field]: value },
    }));
  };

  const handlePrevMonth = () => {
    if (month === 1) {
      setYear((y) => y - 1);
      setMonth(12);
    } else {
      setMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    if (month === 12) {
      setYear((y) => y + 1);
      setMonth(1);
    } else {
      setMonth((m) => m + 1);
    }
  };

  const handleSave = async () => {
    const entries = days
      .filter((day) => !day.is_holiday)
      .map((day) => {
        const row = rows[day.date];
        if (!row) return null;
        const clockInChanged = row.clockIn !== row.originalClockIn;
        const clockOutChanged = row.clockOut !== row.originalClockOut;
        if (!clockInChanged && !clockOutChanged) return null;
        return {
          date: day.date,
          first_clock_in: row.clockIn ? `${row.clockIn}:00` : null,
          last_clock_out: row.clockOut ? `${row.clockOut}:00` : null,
        };
      })
      .filter(Boolean);

    if (entries.length === 0) {
      setMessage({ type: "info", text: t("monthlyOverride.noChanges") });
      return;
    }

    setIsSaving(true);
    setMessage(null);
    try {
      const body: Record<string, unknown> = { year, month, entries };
      if (canSelectEmployee && selectedEmpId) {
        body.emp_id = selectedEmpId;
      }
      const result = await apiClient.put<BulkOverrideResponse>("/api/attendance/override-bulk", body);
      setMessage({
        type: "success",
        text: t("monthlyOverride.saveSuccess", { count: result.updated_count }),
      });
      await fetchData(year, month, targetEmpId);
    } catch {
      setMessage({ type: "error", text: t("monthlyOverride.saveError") });
    } finally {
      setIsSaving(false);
    }
  };

  const getStatusLabel = (status: string | undefined): string => {
    if (!status) return "";
    const statusMap: Record<string, string> = {
      NORMAL: t("attendance.statusNormal"),
      LATE: t("attendance.statusLate"),
      EARLY_LEAVE: t("attendance.statusEarlyLeave"),
      LATE_AND_EARLY_LEAVE: t("attendance.statusLateAndEarlyLeave"),
      ABNORMAL: t("attendance.statusAbnormal"),
    };
    return statusMap[status] ?? status;
  };

  const getStatusColor = (status: string | undefined): string => {
    if (!status) return "";
    const colorMap: Record<string, string> = {
      NORMAL: "text-green-700 bg-green-100",
      LATE: "text-red-700 bg-red-100",
      EARLY_LEAVE: "text-amber-700 bg-amber-100",
      LATE_AND_EARLY_LEAVE: "text-red-700 bg-red-100",
      ABNORMAL: "text-gray-700 bg-gray-100",
    };
    return colorMap[status] ?? "";
  };

  const getDayType = (day: WorkdayInfo): string => {
    if (day.is_makeup_workday) return t("monthlyOverride.makeupWorkday");
    if (day.is_holiday && day.description) return day.description;
    if (day.is_holiday) {
      const weekday = new Date(day.date).getDay();
      return weekday === 0 || weekday === 6
        ? t("monthlyOverride.weekend")
        : t("monthlyOverride.holiday");
    }
    return t("monthlyOverride.workday");
  };

  const summaryByDate: Record<string, DailyAttendanceSummary> = {};
  for (const s of summaries) {
    summaryByDate[s.date] = s;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 p-4">
        <p className="text-center text-gray-500">{t("common.loading")}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 max-w-5xl mx-auto">
      {/* Back button */}
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 mb-4"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("common.backToDashboard")}
      </Link>

      {/* Header */}
      <h1 className="text-2xl font-bold text-gray-900 mb-1">
        {t("monthlyOverride.title")}
      </h1>
      <p className="text-gray-500 text-sm mb-4">{t("monthlyOverride.subtitle")}</p>

      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-4 mb-4">
        {/* Month selector */}
        <div className="flex items-center gap-2">
          <button
            onClick={handlePrevMonth}
            className="p-1 rounded hover:bg-gray-200"
            aria-label={t("monthlyOverride.previousMonth")}
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="text-lg font-semibold min-w-[120px] text-center">
            {year} / {String(month).padStart(2, "0")}
          </span>
          <button
            onClick={handleNextMonth}
            className="p-1 rounded hover:bg-gray-200"
            aria-label={t("monthlyOverride.nextMonth")}
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>

        {/* Employee selector (HR+ only) */}
        {canSelectEmployee && (
          <select
            value={selectedEmpId ?? ""}
            onChange={(e) => setSelectedEmpId(e.target.value || null)}
            className="border rounded px-3 py-1.5 text-sm"
          >
            <option value="">{t("monthlyOverride.selectEmployee")}</option>
            {employees.map((emp) => (
              <option key={emp.emp_id} value={emp.emp_id}>
                {emp.emp_id} - {emp.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Message */}
      {message && (
        <div
          className={`rounded p-3 text-sm mb-4 ${
            message.type === "success"
              ? "bg-green-100 text-green-800"
              : message.type === "error"
                ? "bg-red-100 text-red-800"
                : "bg-blue-100 text-blue-800"
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Calendar table */}
      <div className="bg-white rounded-lg shadow overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-100 border-b">
              <th className="px-3 py-2 text-left">{t("monthlyOverride.date")}</th>
              <th className="px-3 py-2 text-left">{t("monthlyOverride.day")}</th>
              <th className="px-3 py-2 text-left">{t("monthlyOverride.type")}</th>
              <th className="px-3 py-2 text-left">{t("monthlyOverride.clockIn")}</th>
              <th className="px-3 py-2 text-left">{t("monthlyOverride.clockOut")}</th>
              <th className="px-3 py-2 text-left">{t("monthlyOverride.status")}</th>
            </tr>
          </thead>
          <tbody>
            {days.map((day) => {
              const isEditable = !day.is_holiday;
              const row = rows[day.date];
              const summary = summaryByDate[day.date];

              return (
                <tr
                  key={day.date}
                  className={`border-b ${
                    day.is_holiday
                      ? "bg-gray-50 text-gray-400"
                      : day.is_makeup_workday
                        ? "bg-amber-50"
                        : ""
                  }`}
                >
                  <td className="px-3 py-2 font-mono">{day.date}</td>
                  <td className="px-3 py-2">{day.weekday_zh}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        day.is_makeup_workday
                          ? "bg-amber-200 text-amber-800"
                          : day.is_holiday
                            ? "bg-gray-200 text-gray-600"
                            : "bg-blue-100 text-blue-700"
                      }`}
                    >
                      {getDayType(day)}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {isEditable ? (
                      <input
                        type="time"
                        data-testid="clock-in-input"
                        value={row?.clockIn ?? ""}
                        onChange={(e) => handleTimeChange(day.date, "clockIn", e.target.value)}
                        className="border rounded px-2 py-1 text-sm w-28"
                      />
                    ) : (
                      <span>—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {isEditable ? (
                      <input
                        type="time"
                        data-testid="clock-out-input"
                        value={row?.clockOut ?? ""}
                        onChange={(e) => handleTimeChange(day.date, "clockOut", e.target.value)}
                        className="border rounded px-2 py-1 text-sm w-28"
                      />
                    ) : (
                      <span>—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {summary?.status && (
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(summary.status)}`}
                      >
                        {getStatusLabel(summary.status)}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Save button */}
      <div className="mt-4 flex justify-end">
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="inline-flex items-center gap-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save className="h-4 w-4" />
          {isSaving ? t("monthlyOverride.saving") : t("monthlyOverride.save")}
        </button>
      </div>
    </div>
  );
}
```

### Step 3: Run tests to verify they pass

- [ ] Run:

```bash
cd frontend && npx vitest run __tests__/unit/app/monthly-override.test.tsx
```

Expected: All 7 tests PASS

### Step 4: Commit

- [ ] Commit:

```bash
git add frontend/src/app/dashboard/monthly-override/page.tsx frontend/__tests__/unit/app/monthly-override.test.tsx
git commit -m "feat: add monthly punch override page with calendar table"
```

---

## Task 9: Dashboard Quick Action & Admin Calendar Status

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx`
- Modify: `frontend/src/app/admin/page.tsx`

### Step 1: Add dashboard link to monthly override

- [ ] Add to `frontend/src/app/dashboard/page.tsx` — in the navigation links section, add a new `NavLinkCard` for monthly override:

```tsx
<NavLinkCard
  href="/dashboard/monthly-override"
  icon={<Calendar className="h-6 w-6" />}
  title={t("monthlyOverride.title")}
  description={t("monthlyOverride.subtitle")}
/>
```

Add `Calendar` to the lucide-react import. Add the i18n keys reference.

This card should be visible to all authenticated users (EMPLOYEE and above).

### Step 2: Add CalendarStatusSection to admin page

- [ ] Add to `frontend/src/app/admin/page.tsx` — a new section component visible to HR+ only:

```tsx
function CalendarStatusSection() {
  const t = useTranslations();
  const [calendars, setCalendars] = useState<CalendarStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshingYear, setRefreshingYear] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    apiClient
      .get<CalendarStatusResponse>("/api/config/workdays/status")
      .then((data) => {
        setCalendars([...data.calendars]);
        setIsLoading(false);
      })
      .catch(() => setIsLoading(false));
  }, []);

  const handleRefresh = async (year: number) => {
    setRefreshingYear(year);
    setMessage(null);
    try {
      const result = await apiClient.post<{ year: number; count: number }>(
        `/api/config/workdays/refresh?year=${year}`
      );
      setMessage({
        type: "success",
        text: t("calendarStatus.refreshSuccess", { count: result.count }),
      });
      // Refresh status
      const data = await apiClient.get<CalendarStatusResponse>("/api/config/workdays/status");
      setCalendars([...data.calendars]);
    } catch {
      setMessage({ type: "error", text: t("calendarStatus.refreshError") });
    } finally {
      setRefreshingYear(null);
    }
  };

  if (isLoading) return null;

  return (
    <section className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">{t("calendarStatus.title")}</h2>

      {message && (
        <div
          className={`rounded p-3 text-sm mb-4 ${
            message.type === "success" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
          }`}
        >
          {message.text}
        </div>
      )}

      <table className="w-full text-sm mb-4">
        <thead>
          <tr className="border-b">
            <th className="text-left py-2">{t("calendarStatus.year")}</th>
            <th className="text-left py-2">{t("calendarStatus.status")}</th>
            <th className="text-left py-2">{t("calendarStatus.lastUpdated")}</th>
            <th className="text-left py-2">{t("calendarStatus.updatedBy")}</th>
            <th className="py-2"></th>
          </tr>
        </thead>
        <tbody>
          {calendars.map((cal) => (
            <tr key={cal.year} className="border-b">
              <td className="py-2 font-mono">{cal.year}</td>
              <td className="py-2">
                {cal.loaded ? (
                  <span className="text-green-700 bg-green-100 px-2 py-0.5 rounded text-xs">
                    {t("calendarStatus.loaded")} ({cal.entry_count} {t("calendarStatus.entries")})
                  </span>
                ) : (
                  <span className="text-gray-500 bg-gray-100 px-2 py-0.5 rounded text-xs">
                    {t("calendarStatus.notLoaded")}
                  </span>
                )}
              </td>
              <td className="py-2 text-gray-500">
                {cal.updated_at ? new Date(cal.updated_at).toLocaleString() : "—"}
              </td>
              <td className="py-2 text-gray-500">{cal.updated_by ?? "—"}</td>
              <td className="py-2 text-right">
                <button
                  onClick={() => handleRefresh(cal.year)}
                  disabled={refreshingYear === cal.year}
                  className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
                >
                  {refreshingYear === cal.year
                    ? t("calendarStatus.refreshing")
                    : t("calendarStatus.refresh")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
```

Add `CalendarStatus` and `CalendarStatusResponse` to the type imports. Render `<CalendarStatusSection />` inside the HR+ visible area of the admin page.

### Step 3: Commit

- [ ] Commit:

```bash
git add frontend/src/app/dashboard/page.tsx frontend/src/app/admin/page.tsx
git commit -m "feat: add monthly override dashboard link and admin calendar status section"
```

---

## Task 10: Run All Tests & Final Verification

### Step 1: Run all backend tests

- [ ] Run:

```bash
cd backend && python -m pytest -v
```

Expected: All tests PASS (existing 225 + new ~23 = ~248)

### Step 2: Run all frontend tests

- [ ] Run:

```bash
cd frontend && npx vitest run
```

Expected: All tests PASS (existing 61 + new 7 = ~68)

### Step 3: Verify frontend builds

- [ ] Run:

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no errors

### Step 4: Update TODO.md

- [ ] Update `TODO.md` Phase 13B section — mark all items as `[x]` done. Update test count summary.

### Step 5: Update CLAUDE.md

- [ ] Add design decision #22 about Taiwan workday calendar:

```
22. **Taiwan workday calendar** — Auto-fetched from ruyut/TaiwanCalendar CDN (sourced from 行政院人事行政總處), cached in `system_config` table (key `workday_calendar_{year}`). Falls back to Mon-Fri if fetch fails. HR can manually refresh via admin panel. Used by monthly override page and future Absent Status Tracking (Phase 12).
```

### Step 6: Final commit

- [ ] Commit:

```bash
git add TODO.md CLAUDE.md
git commit -m "docs: update TODO.md and CLAUDE.md for Phase 13B completion"
```
