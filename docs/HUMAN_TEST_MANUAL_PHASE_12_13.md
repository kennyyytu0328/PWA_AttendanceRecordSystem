# Human Test Manual — Phase 12 & 13

Covers Phase 12 (**Absent Status Tracking**) and Phase 13 (**Monthly Punch Override** + **Team Reason Column** + **Taiwan Workday Calendar**). Follow the Prerequisites section in `HUMAN_TEST_MANUAL.md` first — seed users and environment are identical.

## Prerequisites

### Environment Setup

1. Backend: `cd backend && uvicorn app.main:app --reload --port 8000`
2. Frontend: `cd frontend && npm run dev`
3. PostgreSQL: `docker-compose up db -d`
4. Migrations: `cd backend && alembic upgrade head`
   - Verify the enum now includes `ABSENT`:
     ```bash
     psql -U postgres -d attendance -c "SELECT unnest(enum_range(NULL::attendancestatus));"
     ```
     Expected: `NORMAL, LATE, EARLY_LEAVE, LATE_AND_EARLY_LEAVE, ABNORMAL, ABSENT`

### Seed Data

Reuse the users from `HUMAN_TEST_MANUAL.md`:

| emp_id | password | role | department |
|--------|----------|------|------------|
| ADMIN01 | admin123 | ADMIN | IT |
| HR01 | hr123456 | HR | HR |
| MGR01 | mgr12345 | MANAGER | Engineering |
| EMP01 | emp12345 | EMPLOYEE | Engineering |
| EMP02 | emp12345 | EMPLOYEE | Sales |

Make sure all employees have a valid `shift_start_time` (e.g. 09:00) and `shift_end_time` (e.g. 18:00).

### Date Selection Tips

Phase 12 behavior is date-dependent. Choose dates deliberately for each test:

- **Workday (no holiday):** pick a Tue/Wed/Thu without a national holiday, e.g. `2026-04-08`
- **Weekend:** any Sat/Sun, e.g. `2026-04-11` (Saturday)
- **Taiwan national holiday:** `2026-01-01` (New Year's Day), `2026-02-16`–`2026-02-20` (Spring Festival 2026). If unsure, use the `/admin` → "行事曆狀態" section to verify after refreshing.
- **補班 workday:** rare; check the refreshed calendar to find one (e.g. 2025 had several make-up Saturdays).

---

## Test Suite 12: Absent Status Tracking (Phase 12)

Preconditions:
- HR refreshed the current year's Taiwan calendar at least once — see TC-13.4 below (do that suite first if the calendar has never been fetched).
- At least two employees (`EMP01`, `EMP02`) exist.

### TC-12.1: ABSENT created for a non-punching employee on a workday

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Pick a workday in the past where `EMP02` has **no** punches (e.g. `2026-04-08`) | Prerequisite |
| 2 | Login as `EMP01`, add punches for the same date (use TC-13.5 monthly override — fastest) | EMP01 has clock-in/out; EMP02 has none |
| 3 | Login as `ADMIN01`, call `POST /api/reports/generate?date=2026-04-08` | **200 OK**, `generated_count` ≥ 2 |
| 4 | Login as `MGR01`, call `GET /api/reports/daily?start_date=2026-04-08&end_date=2026-04-08` | Returns array with both EMP01 and EMP02 |
| 5 | Inspect the EMP02 row | `status = "ABSENT"`, `first_clock_in = null`, `last_clock_out = null` |
| 6 | Inspect the EMP01 row | `status = "NORMAL"` (or whatever the times imply) |

### TC-12.2: No ABSENT generation on a holiday

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Pick a Taiwan public holiday, e.g. `2026-01-01` | Prerequisite |
| 2 | Confirm no employee has punches on that date | Clean slate |
| 3 | Login as `ADMIN01`, call `POST /api/reports/generate?date=2026-01-01` | **200 OK**, `generated_count = 0` |
| 4 | `GET /api/reports/daily?start_date=2026-01-01&end_date=2026-01-01` as MGR01 | Empty array — no ABSENT rows were created |

### TC-12.3: No ABSENT generation on a weekend

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Pick a Saturday, e.g. `2026-04-11` | Prerequisite |
| 2 | Confirm no employee has punches | Clean slate |
| 3 | Login as `ADMIN01`, call `POST /api/reports/generate?date=2026-04-11` | **200 OK**, `generated_count = 0` |
| 4 | `GET /api/reports/daily?start_date=2026-04-11&end_date=2026-04-11` | Empty array |
| 5 | Repeat with Sunday `2026-04-12` | Same result |

### TC-12.4: ABSENT generation on a 補班 make-up workday

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Find a 補班 Saturday via calendar status (`/admin` → "行事曆狀態" or via `GET /api/config/workdays?year=2025&month=N`) | A date where `is_holiday=false` and description contains `補行上班` or `補班` |
| 2 | Ensure `EMP01` has no punches that day | Clean slate |
| 3 | ADMIN triggers `POST /api/reports/generate?date=<makeup-date>` | `generated_count ≥ 1` |
| 4 | `GET /api/reports/daily` for that date | EMP01 appears with `status = "ABSENT"` |

### TC-12.5: ABSENT status badge in Team page

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as MGR01, open `/team` | Team attendance page loads |
| 2 | Set both date filters to the workday used in TC-12.1 | Page refreshes |
| 3 | Observe rows for EMP02 (who was ABSENT) | Status column shows a **red** `Absent` (English) / `缺勤` (Chinese) badge |
| 4 | Switch language via the language switcher | Badge label updates to the other locale |

### TC-12.6: ABSENT in Reports page with filter

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as HR01, open `/reports` → Daily Report section | Report loads |
| 2 | Set date range to cover TC-12.1's workday | Data populates |
| 3 | Open the Status dropdown | Options include both `ABNORMAL` and `ABSENT` as **separate** items |
| 4 | Filter by `ABSENT` | Only ABSENT rows remain; EMP02 visible |
| 5 | Filter by `ABNORMAL` | Different set — single-punch edge cases, not ABSENT |
| 6 | Observe badge color | Red background with `ABSENT` label |

### TC-12.7: ABSENT visible in personal attendance history

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP02`, open `/attendance` | Page loads |
| 2 | Set date range to include TC-12.1's workday | Records list loads |
| 3 | Observe the ABSENT day | The day appears in the summary-status area (even with no punch rows); status badge is red `Absent` / `缺勤` |

> Note: If EMP02 has no punches at all, some rows may be empty. The status badge is driven by the daily summary, not the log table.

### TC-12.8: Export includes ABSENT rows

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as HR01, open `/reports` → Export section | Form visible |
| 2 | Set date range to include TC-12.1's workday, format = **CSV** | Export succeeds |
| 3 | Open the downloaded CSV | EMP02 row present with `status = ABSENT`, empty `first_clock_in`/`last_clock_out` |
| 4 | Re-export as **JSON** | Same data shape, `status: "ABSENT"` |
| 5 | Re-export as **Excel** | `.xlsx` opens in Excel/LibreOffice; ABSENT row present with empty time cells |

### TC-12.9: Monthly override replaces an ABSENT with the calculated status

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Starting from TC-12.1 result — EMP02 has `ABSENT` for `2026-04-08` | Prerequisite |
| 2 | Login as `EMP02`, open `/dashboard/monthly-override` | Calendar table loads |
| 3 | On `2026-04-08`, enter clock-in `09:00` and clock-out `18:00`, click Save All | Success toast |
| 4 | HR01 `GET /api/reports/daily?start_date=2026-04-08&end_date=2026-04-08` | EMP02 row now shows `status = "NORMAL"` with the new times (no duplicate rows) |
| 5 | On the Team page, refresh the same date | Badge changes from red `Absent` to green `Normal` |

### TC-12.10: Re-running generate is idempotent

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ADMIN calls `POST /api/reports/generate?date=2026-04-08` a second time | **200 OK** |
| 2 | `generated_count` equals the same number as the first run | No duplicate rows created |
| 3 | `GET /api/reports/daily` for that date | Exactly one row per employee |

---

## Test Suite 13: Monthly Punch Override, Reason Column & Taiwan Calendar (Phase 13)

### TC-13.1: Team page Reason column (13A)

Preconditions: at least one employee has a submitted LATE reason.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` and punch at `09:20` (shift starts 09:00, grace 5 min) | LATE alert appears |
| 2 | Fill the reason textarea with "Traffic jam" and submit | "Reason submitted" confirmation |
| 3 | Login as `MGR01`, open `/team`, set today's date | Table loads |
| 4 | Observe EMP01's row | Status column shows red `Late` badge; **Reason column** shows "Traffic jam" |
| 5 | On a row with no reason (another employee) | Reason cell is empty |
| 6 | Inspect `GET /api/reports/daily?start_date=<today>&end_date=<today>` as MGR01 | Response JSON contains `reason` field per row (null or string) |

### TC-13.2: Reason column appears only on first row of a group

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | With an employee who has multiple punches on one day (e.g. EMP01 with clock-in + clock-out) | Prerequisite |
| 2 | Open `/team` as MGR01 | Multiple rows per employee per date |
| 3 | Observe the Reason cell | Appears **only on the first row** of the employee+date group (same as Status and Employee ID columns) |

### TC-13.3: Taiwan calendar — first fetch & status (13B)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `HR01`, open `/admin` and scroll to "Calendar Status" / "行事曆狀態" section | Section visible |
| 2 | Before refresh — rows for current-1, current, current+1 years | Shows "Not loaded" for empty years |
| 3 | Click "更新全年行事曆" / "Refresh Full Year" for current year | Success toast; entry count > 300 |
| 4 | Row updates | Shows loaded=true, updated_at timestamp, updated_by = HR01, entry count |
| 5 | Open DevTools Network tab during refresh | Request to `POST /api/config/workdays/refresh?year=<year>` returns 200 |

### TC-13.4: Non-HR cannot refresh calendar

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as MGR01 | Token obtained |
| 2 | `POST /api/config/workdays/refresh?year=2026` with MGR01 token | **403 Forbidden** |
| 3 | `GET /api/config/workdays/status` with MGR01 token | **403 Forbidden** |
| 4 | Repeat with EMP01 | Both endpoints **403** |

### TC-13.5: Monthly override page — own records (employee self-serve)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01`, click "Monthly Punch Override" card on dashboard | Navigates to `/dashboard/monthly-override` |
| 2 | Observe the month calendar table | Shows every day of the current month, workdays editable, holidays greyed out |
| 3 | Weekends (Sat/Sun) rows | Greyed-out background, inputs disabled |
| 4 | Taiwan national holidays | Greyed-out, label shows holiday description |
| 5 | 補班 rows | Amber badge next to the date |
| 6 | Fill clock-in `09:00` and clock-out `18:00` for three separate workdays | Inputs accept the values |
| 7 | Click "Save All" | Success feedback showing "3 days updated" (or similar) |
| 8 | Reload the page | The three days now show the saved values |

### TC-13.6: Monthly override — verify audit trail preserved

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | As EMP01, punch normally today at (say) `09:15` via `/punch` | Log row created |
| 2 | Open monthly override, change today's clock-in to `09:00`, Save | Success |
| 3 | As HR01 (or directly in DB): `SELECT * FROM attendance_logs WHERE emp_id='EMP01' AND DATE(timestamp) = CURRENT_DATE ORDER BY id;` | **Both** the original 09:15 row (`is_overridden=true`) and the new 09:00 row (`is_overridden=false`) are present |
| 4 | Get today's daily summary via `GET /api/reports/daily?...` | `first_clock_in` reflects the **new** 09:00 (not 09:15), status = `NORMAL` |

### TC-13.7: Monthly override — HR overrides any employee

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as HR01, open `/dashboard/monthly-override` | Employee selector dropdown visible |
| 2 | Select `EMP02` in the dropdown | Calendar re-loads with EMP02's data |
| 3 | Edit clock-in/out for one workday, Save | Success |
| 4 | Verify via `GET /api/reports/daily` filtered by `emp_id=EMP02` | Updated values reflected |
| 5 | Login as `MGR01`, open the same page | Dropdown is **not** visible (managers can't bulk edit others via this page) |

### TC-13.8: Monthly override — employee cannot select other employees

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01`, open `/dashboard/monthly-override` | Page loads |
| 2 | Look for employee selector dropdown | **Not present** — employees can only edit themselves |
| 3 | Via DevTools/curl, attempt `PUT /api/attendance/override-bulk` with `emp_id=EMP02` in the body and EMP01's token | **403 Forbidden** |

### TC-13.9: Monthly override — pre-fill future days

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | As EMP01, navigate to the current month in `/dashboard/monthly-override` | Calendar shown |
| 2 | Pick a future workday (e.g. 5 days ahead), enter `09:00`/`18:00`, Save | Success (future dates allowed for end-of-month salary pre-settlement) |
| 3 | `GET /api/attendance/summaries` as EMP01 | New summary present for the future date with status NORMAL |
| 4 | Re-open the monthly override page | Pre-filled values are still visible |

### TC-13.10: Monthly override — empty save is rejected

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | As EMP01, open monthly override and clear all time inputs | Form shows no values |
| 2 | Click Save All with no changes | **400** or a friendly validation message — no DB writes |
| 3 | `PUT /api/attendance/override-bulk` with empty `entries: []` | **400 Bad Request** |

### TC-13.11: Monthly override — validation of invalid time

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter clock-in `18:00` and clock-out `09:00` (clock-out before clock-in) on a single row | UI should display an error or the backend should reject |
| 2 | Click Save | Either UI blocks save, or backend returns **400**; no new log created |

### TC-13.12: Monthly override — loads via cached calendar, not CDN

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | HR has previously refreshed current-year calendar (TC-13.3) | Prerequisite |
| 2 | Disable internet on the test machine | Simulated offline |
| 3 | As EMP01, open `/dashboard/monthly-override` | Calendar table still renders with holidays/weekends correctly identified (served from `system_config` cache) |
| 4 | Re-enable internet | No-op |

### TC-13.13: Workdays API — public read-only access

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | As `EMP01`, `GET /api/config/workdays?year=2026&month=4` | **200 OK** — array of day objects |
| 2 | Each day has: `date`, `weekday_zh`, `is_holiday`, `description`, `is_makeup_workday` | Schema check |
| 3 | As unauthenticated (no token) | **401 Unauthorized** |

### TC-13.14: Team Reason column — i18n

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | On `/team` as MGR01, note the Reason column header in English | Shows "Reason" |
| 2 | Switch to Chinese | Header shows "事由" |
| 3 | Reason cell content remains the raw employee-entered text (not translated) | Unchanged text |

---

## Regression Checklist (Phase 12/13 did not break prior features)

Run these quick sanity tests after Phase 12/13 changes:

| # | Scenario | Expected |
|---|----------|----------|
| R1 | Regular punch flow (TC-2.1 from main manual) | Still works |
| R2 | Late punch → tardiness alert + reason submission | Still works |
| R3 | Daily report for a date with only punched employees on a weekend | No ABSENT rows — summaries only for those who punched |
| R4 | Export CSV for a single employee (`emp_id` filter) | Still works, ABSENT rows included when applicable |
| R5 | Dashboard quick-action links | Monthly Override card visible and navigates correctly |
| R6 | Admin department management | Unchanged behavior |
| R7 | Language switch on every page | All new Phase 12/13 labels translate (`statusAbsent`, `team.reason`, monthly override strings) |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Calendar page shows every day as a workday | Taiwan calendar never cached; CDN fetch failed at page load | HR runs TC-13.3 to refresh; verify internet access from backend |
| ABSENT not created for a clearly-missed workday | Date happens to be a holiday in the cached calendar | Check `GET /api/config/workdays/status` and inspect the day's `is_holiday` field; refresh if wrong |
| ABSENT created on what should be a holiday | Calendar not cached for that year, falling back to Mon-Fri rule | HR refreshes that specific year |
| Monthly override save shows success but data doesn't persist | Timezone mismatch between client and server | Check server time; check that date inputs use the same timezone as `attendance_logs.timestamp` |
| Team page shows "Abnormal" instead of "Absent" | Frontend cache / old build | Hard reload (Ctrl+Shift+R); confirm `statusAbsent` key exists in `en.json` / `zh.json` |
| `POST /api/reports/generate` returns 500 after migration | `alembic upgrade head` not run after Phase 12 pull | Run migrations — enum needs `ABSENT` value |
