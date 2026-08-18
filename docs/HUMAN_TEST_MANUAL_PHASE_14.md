# Human Test Manual — Phase 14 (2026-08 Monthly Patch)

Covers `late_leave_reason` + the punch-page **confirm-only late dialog**, the **dual submission gate**, the **HRM export**, **export exclusion**, the **monthly-override lock**, `/api/auth/me` shift times, the **schedule-confirmation banner**, and the **延後下班原因 export column** (CSV/JSON/Excel) — plus the fixes applied after code review (seconds-precision gate, read-only-not-blank lock display, server-gate bypass close).

> **The one-line behavior to verify:** a punch that clocks out **after shift end on a workday** needs a reason (ASSIGNED_OVERTIME or PERSONAL) before the month can be submitted — enforced both in the UI and on the server, at **minute precision**. Locking the month for settlement makes the page **read-only** (values still visible), never blank.

---

## Prerequisites

### Environment
1. PostgreSQL: `docker-compose up db -d`
2. Backend: `cd backend && alembic upgrade head && uvicorn app.main:app --reload --port 8000`
3. Frontend: `cd frontend && npm run dev`

### Seed users (`cd backend && python seed.py`)
| emp_id | password | role | department | name | shift |
|--------|----------|------|------------|------|-------|
| ADMIN01 | admin123 | ADMIN | IT | Admin User | 09:00–18:00 |
| HR01 | hr123456 | HR | HR | HR Manager | 09:00–18:00 |
| MGR01 | mgr12345 | MANAGER | Engineering | Engineering Manager | 09:00–18:00 |
| EMP01 | emp12345 | EMPLOYEE | Engineering | Alice Engineer | 09:00–18:00 |
| EMP02 | emp12345 | EMPLOYEE | Sales | Bob Sales | 09:00–18:00 |

> Password login works for all seed accounts. WebAuthn is **not** required for this manual.
> Every scenario below assumes shift end **18:00** unless stated otherwise.

### Note on default config (no admin UI for these two)
- `export_excluded_emp_ids` defaults to `["HR01", "ADMIN"]`. The seeded HR account **is** `HR01`, so it will vanish from every export by default (Scenario E uses this). The seeded admin account is `ADMIN01`, which does **not** match the literal string `"ADMIN"` — it stays visible in exports unless you change the config.
- `late_reason_required_leave_types` defaults to `["出差"]`.
- Both are `system_config` keys with no admin UI — inspect/change them via `psql` or a direct `PUT` if you need non-default values:
  ```bash
  psql -U postgres -d attendance -c "select key, value from system_config where key in ('export_excluded_emp_ids','late_reason_required_leave_types');"
  ```

---

## Scenario A — Confirm-only late dialog on the punch page

1. Log in as **EMP01**. Make sure your system clock (or the server's) is **past 18:00** on a weekday (a normal Mon–Fri, not a holiday).
2. Open **`/punch`** and tap **Punch**.
   - ✅ **Expected:** a dialog appears (no free-text box) with two options: **A: Supervisor-assigned overtime** and **B: Stayed in the office for personal reasons**, defaulting to **B**. The punch has **not** been submitted yet.
3. Click **Confirm** without changing the selection.
   - ✅ **Expected:** the punch submits with `late_leave_reason = "PERSONAL"`. No dialog on a normal on-time punch (test before 18:00 as a control — no dialog, submits immediately).
4. Repeat, this time selecting **A** before confirming.
   - ✅ **Expected:** submits with `late_leave_reason = "ASSIGNED_OVERTIME"`.
5. **Weekend/holiday control:** if today happens to be Saturday/Sunday or a national holiday, punching after 18:00 must **not** show the dialog at all (no shift on a non-working day) — it submits directly with no `late_leave_reason`. If you can't wait for a real holiday, this is also covered by an automated test; feel free to skip the manual check.

---

## Scenario B — Monthly-override page: red-flagged rows + editable late-reason column

1. Log in as **EMP01**, open **`/dashboard/monthly-override`** for the current month.
2. Find (or create, via **Save**) a day with a clock-out **after 18:00** and no late reason selected.
   - ✅ **Expected:** the row is highlighted red with a ⚠ icon next to the **late-reason** dropdown; the dropdown itself has a red border.
3. Select a reason (A or B) for that row and click **Save**.
   - ✅ **Expected:** "Saved" toast; the red highlight and ⚠ disappear on reload.
4. Set a clock-out at **exactly 18:00:00** (no seconds) on another day, leave the reason blank.
   - ✅ **Expected:** row is **not** flagged — 18:00 sharp is on time, not late.

---

## Scenario C — Seconds-precision fix (review fix #1)

This is the regression the code review caught: the backend used to compare full-precision timestamps while the UI compares `"HH:MM"`, so a clock-out landing in the *same minute* as shift end could pass the UI's check but still fail the server's.

1. As **EMP01**, use **Monthly Override** to set a clock-out of **18:00** for a workday (the UI only accepts `HH:MM`, so this alone can't reproduce the bug — it's a live-punch scenario).
2. To actually exercise it, punch live at **18:00:0X** (any few seconds past the top of the minute — e.g. wait until 17:59:58 and tap Punch at 18:00:02).
   - ✅ **Expected:** **no** late-reason dialog appears (the punch page's own check already truncates to the minute) — this submits immediately.
3. Now try **本月送單 / Submit Month** for that day's month.
   - ✅ **Expected:** submission **succeeds** — the server-side gate also treats `18:00:02` as on-time (minute-truncated), so it does not block on a day the UI already treated as clean.
   - ❌ **Pre-fix behavior (do not expect this):** a 400 with `late_reason_missing` even though nothing on screen looked late.

---

## Scenario D — Dual submission gate (client hard-block + server 400)

1. As **EMP01**, create a late clock-out (after 18:00, e.g. 19:00) with **no** reason selected, and **leave the page without saving the reason** (or use the API directly, see step 3).
2. Click **本月送單 / Submit Month** on the monthly-override page.
   - ✅ **Expected:** a modal lists the offending date(s) and blocks submission client-side — no network call happens.
3. Bypass the UI and hit the API directly to confirm the server enforces independently:
   ```bash
   # TOKEN = EMP01's JWT (browser devtools → Application → Local Storage → token)
   curl -i -X POST http://localhost:8000/api/monthly-submissions \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"emp_id":"EMP01","year":2026,"month":<current month>}'
   ```
   - ✅ **Expected:** `400 Bad Request` with `detail.code = "late_reason_missing"` and `detail.dates` listing the offending date.
4. Go back, select a reason, save, and retry Submit Month.
   - ✅ **Expected:** succeeds (`200`).

---

## Scenario E — Server-gate bypass closed (review fix #4)

Before the fix, the server-side gate only scanned **already-materialized** summary rows. A month nobody had opened in the monthly-override UI yet (so no summary row existed) could be submitted via direct API even with a late, unexplained punch sitting in the raw logs.

1. Pick an employee/month combination that has **never been opened** in `/dashboard/monthly-override` (fresh seed data works, or use a brand-new test employee).
2. Have that employee punch in on-time and punch out **after 18:00** on a workday, via `/punch` — but do **not** visit the monthly-override page for that month afterward, and do **not** select a late reason.
3. Call the submission API directly for that month (same `curl` as Scenario D step 3, with that employee's token/emp_id/month).
   - ✅ **Expected:** still `400` with `late_reason_missing` listing that date — the backend regenerates the day's summary from the raw punch log before scanning, so it can't be silently skipped just because no one loaded the page first.

---

## Scenario F — Monthly-override lock: read-only, not blank (review fix #2)

1. Log in as **HR01**, open **`/admin`** → find the **override lock** section → toggle it **ON** ("locked").
2. Log in as **EMP01**, open **`/dashboard/monthly-override`**.
   - ✅ **Expected:** a red banner appears explaining the page is closed for month-end settlement ("人資月結作業中…" / "Month-end settlement in progress…").
   - ✅ **Expected:** every day that would normally be editable (workdays, 補班 Saturdays) shows its **stored values as plain text** — clock-in, clock-out, late reason, leave type, remark, overtime hours — **not** a blank `-`. Only genuinely non-editable rows (Sundays, holidays you don't have HR+ access to) show `-`, same as always.
   - ✅ **Expected:** no `<input>`/`<select>` controls appear anywhere; **Save** and **本月送單** buttons are disabled.
3. Log in as **MGR01** and repeat step 2 on their own month.
   - ✅ **Expected:** same read-only-with-visible-values behavior — MANAGER is blocked just like EMPLOYEE.
4. Log in as **HR01** (or **ADMIN01**) and open the same page.
   - ✅ **Expected:** no lock banner, all normal inputs are present and editable — HR/ADMIN are always exempt.
5. As HR01, confirm the API-level lock too:
   ```bash
   curl -i -X PUT http://localhost:8000/api/attendance/override-bulk \
     -H "Authorization: Bearer $EMP_TOKEN" -H "Content-Type: application/json" \
     -d '{"year":2026,"month":<current month>,"entries":[{"date":"2026-08-01","first_clock_in":"09:00","last_clock_out":"18:00"}]}'
   ```
   - ✅ **Expected:** `403 Forbidden` for the EMPLOYEE token while locked; `200` for an HR/ADMIN token.
6. Toggle the lock back **OFF** in `/admin`.
   - ✅ **Expected:** EMP01/MGR01 immediately regain full editing on reload — banner disappears, inputs return.

---

## Scenario G — HRM export

1. Seed at least one full day (clock-in + clock-out) for **EMP01**.
2. Log in as **HR01**, open **`/reports`**, set a date range covering that day, and click the **HRM Export** button (separate from the CSV/JSON/Excel dropdown+Export button).
   - ✅ **Expected:** downloads an `.xlsx` file named `hrm_export_<start>_<end>.xlsx`.
3. Open the file.
   - ✅ **Expected:** **one row per punch** (a full day = 2 rows, not 1), 考勤機ID column is **blank**, the source column reads **"APP打卡"** regardless of whether the punch was a live phone punch, an override, or NFC-imported, and dates are unpadded (`8/1`, not `08/01`).

---

## Scenario H — Export exclusion (`export_excluded_emp_ids`)

1. As **HR01**, export CSV, JSON, Excel, and HRM for a range that includes **HR01's own** attendance (HR01 is in the default exclusion list).
   - ✅ **Expected:** **HR01 never appears** in any of the four export formats, even though HR01 has real attendance data in that range.
2. Try filtering the export explicitly by `emp_id=HR01` (via the Employee dropdown or `?emp_id=HR01` on the export call).
   - ✅ **Expected:** still **empty** — exclusion wins over an explicit employee filter (unlike the terminated-employee override, which does show an explicit `emp_id` even if terminated).
3. Confirm a non-excluded employee (e.g. EMP01) exports normally in the same request.

---

## Scenario I — `/api/auth/me` shift times + format-consistency fix (review fix #6)

1. Log in as any employee and open dev tools → Network → find the `GET /api/auth/me` call.
   - ✅ **Expected:** response includes `name`, `shift_start_time`, and `shift_end_time` as `"HH:MM"` strings (e.g. `"18:00"`, not `"18:00:00"`).
2. As **HR01**, open **`/dashboard/monthly-override`**, select a *different* employee via the employee picker, and repeat Scenario B/C for that employee.
   - ✅ **Expected:** the late-reason red-flagging uses that **selected employee's** shift end (from `/api/employees`, which serializes `"HH:MM:SS"`), not HR01's own — and the boundary is still exact (an exact-shift-end clock-out is never falsely flagged), confirming the two different time formats are now normalized consistently.

---

## Scenario J — Schedule-confirmation banner

1. Log in as **any role** (EMPLOYEE/MANAGER/HR/ADMIN) and open **`/dashboard/monthly-override`**.
   - ✅ **Expected:** an amber notice is visible below the 24-hour time-format hint, stating the month's schedule is deemed accepted absent timely feedback to the supervisor/HR. Visible regardless of lock state or role.

---

## Scenario K — 延後下班原因 column in CSV/JSON/Excel exports

Added after the initial manual (commit `1fee5d4`): the standard exports now carry the late-leave reason.

1. Make sure **EMP01** has at least one workday with a late clock-out (after 18:00) **and** a saved late reason — reuse the day from Scenario B (reason A) or D (after step 4).
2. Log in as **HR01**, open **`/reports`**, set a date range covering that day, and export **CSV**.
   - ✅ **Expected:** a **「延後下班原因」** column appears **after 遲到理由 and before 送單狀態**, showing **「A:主管指派加班」** (ASSIGNED_OVERTIME) or **「B:因個人原因留在辦公室」** (PERSONAL) for that day, and **blank** for days without a reason.
3. Repeat with **Excel**.
   - ✅ **Expected:** same column position and localized labels as CSV.
4. Repeat with **JSON**.
   - ✅ **Expected:** each row carries a `late_leave_reason` field with the **raw enum** (`"ASSIGNED_OVERTIME"` / `"PERSONAL"`, or `null`) — not the Chinese label.
5. Repeat with **HRM Export** (Scenario G's button).
   - ✅ **Expected:** **no** late-reason column — the HRM format's columns are fixed by the external payroll system and intentionally untouched.

---

## Expected-results matrix

| Scenario | Actor | Condition | Expected |
|----------|-------|-----------|----------|
| A | EMP01 | punch after 18:00 on workday | Confirm-only dialog (A/B, default B), blocks submit until confirmed |
| A | EMP01 | punch on weekend/holiday after "shift end" | No dialog, submits directly |
| B | EMP01 | late clock-out, no reason | Row red-flagged; clears after reason saved |
| B | EMP01 | clock-out exactly 18:00:00 | Not flagged |
| C | EMP01 | live punch at 18:00:0X | No dialog; Submit Month succeeds (minute precision both sides) |
| D | EMP01 | Submit Month with missing reason | Client modal blocks; direct API → 400 `late_reason_missing` |
| E | fresh employee/month | late punch, never opened in UI, direct API submit | Still 400 — gate regenerates summary from raw logs first |
| F | EMP01 / MGR01 | lock ON | Read-only banner; **values visible**, not blank; Save/送單 disabled; bulk-override API → 403 |
| F | HR01 / ADMIN01 | lock ON | Fully unaffected — editable, no banner |
| G | HR01 | HRM export | One row per punch; blank 考勤機ID; fixed "APP打卡"; unpadded dates |
| H | HR01 | export incl. HR01 | HR01 excluded from all 4 formats, even by explicit emp_id filter |
| I | any | `GET /api/auth/me` | `shift_end_time` as `"HH:MM"` |
| I | HR01 viewing other emp | override page red-flag logic | Uses target employee's shift, exact-boundary safe despite `"HH:MM:SS"` source |
| J | any role | monthly-override page | Amber schedule-confirmation notice always visible |
| K | HR01 | CSV/Excel export, day with saved reason | 「延後下班原因」 column after 遲到理由, localized A/B label |
| K | HR01 | JSON export | Raw enum under `late_leave_reason`; HRM format has no such column |

---

## Cleanup / reset
- Toggle the **override lock OFF** in `/admin` when done (default state).
- No schema rollback needed for a normal test pass; if you want a clean slate, re-run `python seed.py` against a fresh DB (`alembic downgrade base && alembic upgrade head`).

## Notes / known limitations
- `export_excluded_emp_ids` and `late_reason_required_leave_types` have **no admin UI** — they're `system_config` rows only, edit via SQL/API if you need non-default values for testing.
- The late-reason requirement never consults `AttendanceStatus` — a day marked LATE (late clock-**in**, on-time clock-out) does **not** need a reason; a NORMAL day with a late clock-**out** does. Don't use the status badge as a proxy for "will this be flagged."
- Single-punch days (only a clock-in, no clock-out yet) are always exempt from the late-reason requirement — there's nothing to judge yet.
- A day with a `leave_type` is exempt from the late-reason requirement unless that leave type is in `late_reason_required_leave_types` (default: `出差`, since a business trip can still start late and needs explaining).
