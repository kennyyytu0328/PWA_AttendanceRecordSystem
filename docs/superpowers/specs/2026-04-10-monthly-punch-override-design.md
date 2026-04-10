# Phase 13B: Monthly Punch Override & Taiwan Workday Calendar

**Date:** 2026-04-10
**Status:** Approved
**Scope:** Monthly punch override for employees + Taiwan workday calendar integration

## Overview

Employees can bulk-edit their first clock-in and last clock-out times for any workday of the month via a full calendar table page. Overrides take effect immediately (no approval workflow). Original raw punch records are preserved for HR/Manager audit. Employees can pre-fill future days for end-of-month salary settlement.

HR+ can override any employee's punches via an employee selector dropdown.

Taiwan workday calendar data (from 行政院人事行政總處) is integrated to distinguish workdays, holidays, weekends, and 補班 (make-up workdays). This also unblocks Phase 12 (Absent Status Tracking) by providing a definitive workday source.

## Taiwan Workday Calendar Data Layer

### Data Source

Static JSON from [ruyut/TaiwanCalendar](https://github.com/ruyut/TaiwanCalendar), originally sourced from 行政院人事行政總處. Each entry:

```json
{"date": "20260101", "week": "四", "isHoliday": "是", "description": "中華民國開國紀念日"}
```

### Backend Utility

New `backend/app/utils/taiwan_calendar.py`:

- `is_workday(date) -> bool` — True if not a holiday/weekend
- `get_workdays_in_month(year, month) -> list[date]` — All workdays in a month
- `get_day_info(date) -> DayInfo` — Returns is_holiday, description, is_makeup_workday (補班)
- `get_month_info(year, month) -> list[DayInfo]` — All days of a month with workday info

### Storage

Calendar data stored in `system_config` table:
- Key: `workday_calendar_{year}` (e.g., `workday_calendar_2026`)
- Value: JSON array of day entries
- Metadata includes `updated_at` timestamp

### Auto-Fetch on Demand

When a year's calendar is requested but not cached:
1. Fetch from ruyut/TaiwanCalendar GitHub raw JSON
2. Parse and save to `system_config` table
3. Fall back to standard Mon-Fri (Sat/Sun = holiday) if fetch fails

HR can manually refresh via admin panel "更新全年行事曆" button.

## API Design

### New Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/config/workdays` | Any auth | `?year=&month=` returns day-by-day info |
| `POST` | `/api/config/workdays/refresh` | HR+ | `?year=` re-fetches calendar from GitHub |
| `GET` | `/api/config/workdays/status` | HR+ | Calendar years loaded + last updated timestamps |
| `PUT` | `/api/attendance/override-bulk` | Any auth | Bulk override punches for a month |

### Bulk Override Request Schema

```python
class BulkOverrideEntry(BaseModel):
    date: date
    first_clock_in: time | None   # null = no change
    last_clock_out: time | None   # null = no change

class BulkOverrideRequest(BaseModel):
    year: int
    month: int
    emp_id: str | None = None  # HR+ only, defaults to self
    entries: list[BulkOverrideEntry]
```

### Bulk Override Logic

1. For each entry, mark existing logs as `is_overridden=True`
2. Create new attendance log entries with the override times
3. Recalculate daily summaries for all affected dates
4. Return updated summaries with new statuses

Original raw punch records in `attendance_logs` are always preserved for HR/Manager audit trail.

### Permission Rules

- **EMPLOYEE**: can only override own punches (`emp_id` must be null or self)
- **HR+**: can override any employee's punches (via `emp_id` parameter)

## Frontend Design

### New Page: `/dashboard/monthly-override`

Full calendar table showing all days of the selected month.

#### Components

- **MonthSelector** — Year/month navigation arrows + display, defaults to current month
- **EmployeeSelector** — Dropdown for HR+ only, fetches employee list from `/api/employees`
- **CalendarTable** — Main table with columns:

| Date | Day | Type | Clock-in | Clock-out | Status |
|------|-----|------|----------|-----------|--------|
| 04/01 | Tue | Workday | `[08:55]` | `[18:02]` | Normal |
| 04/02 | Wed | Workday | `[09:12]` | `[ ]` | Late |
| 04/04 | Fri | Holiday | — | — | — |
| 04/05 | Sat | Weekend | — | — | — |

  - **Workday rows**: Always editable time inputs for clock-in/clock-out, pre-populated from existing summaries
  - **Holiday/weekend rows**: Greyed out, non-editable, show holiday description
  - **補班 rows**: Editable, shown with amber "補班" badge
  - **Status column**: Current calculated status (Normal/Late/Early Leave/etc.)
- **SaveButton** — Collects all modified entries, calls `PUT /api/attendance/override-bulk`, shows success/error feedback with recalculated statuses

#### Dashboard Entry Point

Add a card/button on `/dashboard` page linking to `/dashboard/monthly-override`.

### Admin Panel: Calendar Status Bar (HR+ only)

Displayed on the admin page:
- Current calendar year(s) loaded with checkmark
- Last updated timestamp per year
- "更新全年行事曆" refresh button (triggers `POST /api/config/workdays/refresh`)

### i18n

All user-facing strings use translation keys in `en.json` and `zh.json`. No hardcoded text.

## Test Plan

### Backend Unit Tests

- `test_taiwan_calendar.py` — Parse JSON, `is_workday()`, `get_workdays_in_month()`, holiday detection, 補班 detection, fallback to Mon-Fri when no data
- `test_attendance_service.py` (additions) — `bulk_override_punches()`: creates override logs, preserves originals, recalculates summaries, HR can override others, employee restricted to self
- Workday config tests — auto-fetch, refresh, status reporting

### Backend Integration Tests

- Bulk override API — auth enforcement, validation, role-based access (employee vs HR)
- Workday API — returns correct day info per month, refresh endpoint, status endpoint

### Frontend Unit Tests

- Monthly override page — renders full calendar table, month navigation, all workday rows editable, holiday rows disabled, save flow, error/success feedback
- HR employee selector — visible for HR+, hidden for EMPLOYEE/MANAGER
- CalendarStatusBar — shows loaded years, last updated, refresh button triggers API call
