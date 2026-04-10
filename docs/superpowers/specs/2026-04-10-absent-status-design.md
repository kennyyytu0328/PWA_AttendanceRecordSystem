# Phase 12: Absent Status Tracking

**Date:** 2026-04-10
**Status:** Approved
**Scope:** Generate ABSENT summaries for employees who don't punch on workdays

## Overview

When HR generates daily summaries, the system now also creates ABSENT summaries for employees who didn't punch on that workday. Uses the Taiwan workday calendar (Phase 13B) to determine which dates are workdays. HR can fix false ABSENTs via Monthly Punch Override.

## Backend Changes

### Enum & Migration

- Add `ABSENT` to `AttendanceStatus` enum in `backend/app/models/daily_attendance_summary.py`
- Alembic migration to add the new enum value to PostgreSQL

### Reporting Service

Extend `generate_all_summaries(session, date)` in `backend/app/services/reporting_service.py`:

1. Existing: generate summaries for employees who punched (unchanged)
2. NEW: Check if `date` is a workday via Taiwan calendar (`is_workday_from_data`)
3. If workday: find all employees with no summary for this date → bulk-insert ABSENT summaries (first_clock_in=None, last_clock_out=None, status=ABSENT)
4. If holiday/weekend: skip — no ABSENT generation
5. Return total count (normal + absent)

### Dependencies

- `taiwan_calendar.py` — `is_workday_from_data()`, `parse_calendar_json()`
- `system_config_repository.py` — `get_workday_calendar()` for cached calendar data
- `taiwan_calendar.py` — `fetch_calendar_from_cdn()` as fallback if not cached

## Frontend Changes

### Status Badge

Add ABSENT handling to StatusBadge in:
- `frontend/src/app/team/page.tsx`
- `frontend/src/app/reports/page.tsx`
- `frontend/src/app/attendance/page.tsx`

Color: red background (same as LATE) with "Absent" / "缺勤" text.

### i18n

- `attendance.statusAbsent` — "Absent" / "缺勤" (add to attendance and team sections)
- `reports.statusAbsent` already exists

## Test Plan

### Backend Unit Tests

- `test_generate_all_summaries_creates_absent_for_non_punching` — employees without punches on a workday get ABSENT
- `test_generate_all_summaries_skips_absent_on_holiday` — no ABSENT on holidays
- `test_generate_all_summaries_skips_absent_on_weekend` — no ABSENT on weekends
- `test_absent_summary_has_null_clock_times` — first_clock_in and last_clock_out are None
- `test_override_replaces_absent` — monthly override changes ABSENT to calculated status

### Backend Integration Tests

- `test_generate_summaries_includes_absent_count` — API response includes absent in count
