# Design — Leave Remarks, Monthly Submission, Export Refinements, ADMIN-only Delete

**Date:** 2026-05-14
**Status:** Draft — awaiting user review before implementation planning
**Source:** Meeting minutes 2026-05-13 (9 items)

## 1. Goals

Deliver five related sub-features in a single coordinated change:

| # | Sub-feature | Meeting items covered |
|---|---|---|
| F1 | Leave-type remark system on daily summaries | 1, 2, 3, 7 |
| F2 | Export refinements (Chinese headers, shift-time column, remark column, no late/early-only column) | 4, 5, 6 |
| F3 | ADMIN-only employee deletion (revoke HR's delete permission) | 8 |
| F4 | Monthly-override warning modal on tardy days | 9-a |
| F5 | Monthly submission flag + reports filtering | 9-b |

Non-goals:
- No approval workflow for leave (employees self-serve via remark; no manager approval).
- No locking of submitted months (submissions are status flags, not edit guards).
- No migration of existing `attendance_reasons` rows — those remain in place for their original purpose.

## 2. Data Model Changes

### 2.1 `AttendanceStatus` enum — add `LEAVE`

```python
class AttendanceStatus(str, Enum):
    NORMAL = "NORMAL"
    LATE = "LATE"
    EARLY_LEAVE = "EARLY_LEAVE"
    LATE_AND_EARLY_LEAVE = "LATE_AND_EARLY_LEAVE"
    ABNORMAL = "ABNORMAL"
    ABSENT = "ABSENT"
    LEAVE = "LEAVE"   # NEW
```

Display label: `請假` (zh) / `Leave` (en).

### 2.2 `daily_attendance_summaries` — add two columns

```sql
ALTER TABLE daily_attendance_summaries
  ADD COLUMN leave_type VARCHAR(50) NULL,
  ADD COLUMN remark     VARCHAR(500) NULL;
```

- `leave_type` non-NULL → triggers `LEAVE` status (overrides LATE / EARLY_LEAVE / LATE_AND_EARLY_LEAVE detection).
- `remark` is free-text supplement (e.g., `上午`, `早上 4 小時`). May exist with or without `leave_type`.
- A row with `leave_type=NULL` and `remark="..."` is a pure informational note — it does NOT change status.

### 2.3 `attendance_reasons` — UNCHANGED

The existing table continues to serve its original purpose: post-event explanations for LATE / EARLY_LEAVE / LATE_AND_EARLY_LEAVE punches. Different concept, different write path, different display column.

- No schema change.
- No data migration.
- No join with `daily_attendance_summaries.remark`. The two are independent columns that display side-by-side as `備註` and `遲到理由`.

### 2.4 `system_config` — new key `leave_types`

```json
{
  "types": ["特休", "病假", "事假", "婚假", "喪假", "產假", "公假", "出差", "補休"]
}
```

- Seeded by migration with the 9 defaults above.
- HR+ can update via `/admin` (mirrors existing `departments` management).

### 2.5 `monthly_submissions` — new table

```sql
CREATE TABLE monthly_submissions (
    id           SERIAL PRIMARY KEY,
    emp_id       VARCHAR NOT NULL REFERENCES employees(emp_id),
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    submitted_at TIMESTAMPTZ NOT NULL,
    UNIQUE (emp_id, year, month)
);
CREATE INDEX idx_monthly_submissions_lookup
  ON monthly_submissions (year, month);
```

- One row per (employee, year, month). Upsert on resubmit (refreshes `submitted_at`).
- No locking semantics — submissions are status flags only. Employees may continue editing after submitting; resubmitting updates the timestamp.

## 3. Business Logic

### 3.1 `calculate_status` — leave-type takes priority

```python
def calculate_status(
    shift_start: datetime.time,
    shift_end: datetime.time,
    first_clock_in: datetime.datetime | None,
    last_clock_out: datetime.datetime | None,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
    leave_type: str | None = None,    # NEW
) -> AttendanceStatus | None:
    if leave_type is not None:
        return AttendanceStatus.LEAVE
    # ...existing logic unchanged
```

`generate_daily_summary` reads `leave_type` from any existing summary row (or from the incoming monthly-override payload) and passes it through.

### 3.2 ABSENT vs LEAVE precedence

When a workday has no punches AND no `leave_type`, status remains `ABSENT` (existing behavior).
When a workday has no punches but `leave_type` is set, status is `LEAVE`.
This means an employee on full-day leave can pre-fill `leave_type` for a future day (or back-fill a missed day) and the row will not be flagged ABSENT during `generate_all_summaries`.

### 3.3 Monthly submission service

- `submit_month(emp_id, year, month)` — upserts a row, returns the row.
- `get_submission_status(emp_id, year, month)` — returns submission row or None.
- `is_submitted(emp_id, year, month)` — boolean helper.

### 3.4 Reports — submission filtering

`get_daily_report` and `export_attendance` accept a new `submission_filter` parameter with three values:

| Value | Behavior | UI label |
|---|---|---|
| `"submitted"` (default) | Only rows whose `(emp_id, year-of-date, month-of-date)` exists in `monthly_submissions` | 已送單 |
| `"unsubmitted"` | Only rows whose `(emp_id, year-of-date, month-of-date)` does NOT exist | 未送單 |
| `"all"` | No submission filtering | 全部 |

Rules:
- Explicit `emp_id` does NOT override this filter (only overrides the terminated-employee filter).
- For export: `submission_filter="all"` and `"unsubmitted"` are HR+ only. Non-HR callers are silently forced to `"submitted"`.
- Each returned row carries a `submission_status: "submitted" | "unsubmitted"` field for UI display regardless of filter mode.

## 4. API Changes

### 4.1 New endpoints

| Method | Path | Auth | Body / Query | Returns |
|---|---|---|---|---|
| POST | `/api/monthly-submissions` | EMPLOYEE+ (self only) / HR+ (any) | `{ emp_id, year, month }` | `{ emp_id, year, month, submitted_at }` |
| GET | `/api/monthly-submissions` | EMPLOYEE+ (self) / HR+ (any) | `?emp_id=&year=&month=` | `{ submitted: bool, submitted_at?: string }` |
| GET | `/api/monthly-submissions/list` | HR+ | `?year=&month=&department=` | List of `{ emp_id, name, department, submitted_at \| null }` |
| GET | `/api/admin/leave-types` | All authenticated | — | `{ types: string[] }` |
| PUT | `/api/admin/leave-types` | HR+ | `{ types: string[] }` | `{ types: string[] }` |

### 4.2 Modified endpoints

`POST /api/monthly-override` — each `entries[].day` object accepts two new optional fields:

```typescript
{
  date: "2026-05-13",
  first_clock_in: "08:30" | null,
  last_clock_out: "17:30" | null,
  leave_type: "特休" | null,    // NEW
  remark: "上午" | null         // NEW
}
```

The handler writes both fields to `daily_attendance_summaries` after the punch-log override step. `generate_daily_summary` then computes status from the persisted `leave_type`.

`GET /api/reports/daily` — response rows gain three fields:
- `leave_type: string | null`
- `remark: string | null`
- `submission_status: "submitted" | "unsubmitted"`

`GET /api/reports/export` and `GET /api/reports/daily` — accept:
- `submission_filter: "submitted" | "unsubmitted" | "all"` (default `"submitted"`; non-HR callers silently forced to `"submitted"`).
- Output columns gain `班別時間 / 備註 / 遲到理由 / 送單狀態` (CSV/Excel) or `shift_time / remark / reason / submission_status` (JSON).

`DELETE /api/employees/{id}` — permission downgrade:
- Before: HR+
- After: ADMIN only
- HR receives 403 with a generic permission error.

### 4.3 Auth / permission service

`permission_service.py` — remove `DELETE_EMPLOYEE` from HR's frozenset; keep it in ADMIN's.

## 5. UI Changes

### 5.1 `/dashboard/monthly-override`

Per-row UI gains a 備註 cell containing:
- A `<select>` for leave type (sourced from `/api/admin/leave-types`; first option is `— 無 —` meaning NULL).
- A short `<input type="text" maxLength=500>` for the free-text supplement.

Page header gains a second action button:
- `儲存全部` — existing; before saving, scan filled rows for `LATE / EARLY_LEAVE / LATE_AND_EARLY_LEAVE / ABNORMAL / ABSENT` and open the warning modal if any are found.
- `本月送單` — new; same scan + modal. On confirm, calls `POST /api/monthly-submissions` for the displayed month after the save completes.

Warning modal contents:
- Title: `偵測到 N 個異常日`
- Body: list of `MM/DD — 狀態名稱` (one line per offending day).
- Two buttons: `返回修改` (cancel) | `繼續送出` (proceed with save / submit).
- Modal is informational-only — it never blocks; even ABSENT does not prevent submission.

### 5.2 `/reports`

- Table gains three columns:
  - `班別時間` — `${shift_start} - ${shift_end}` in `HH:MM` 24-hour format (e.g., `08:30 - 17:30`).
  - `備註` — `${leave_type ? leave_type + (remark ? ' · ' + remark : '') : remark ?? ''}`.
  - `送單狀態` — `已送單 ✓` (zh) / `Submitted ✓` (en) or `未送單` / `Unsubmitted`.
- Filter bar gains:
  - `送單狀態` dropdown: `已送單 / 未送單 / 全部` — drives the `submission_filter` API param. Default is `已送單`. For non-HR roles, the dropdown is hidden and the param is forced to `submitted`.
  - The same dropdown value is sent to `/api/reports/export` when the user triggers a download — no separate "include unsubmitted" toggle. HR sees what they download.
- Existing `遲到理由` column (from `attendance_reasons`) is preserved unchanged.

### 5.3 `/admin`

- New tab/section `假別管理` — mirrors the existing departments manager. Add / remove / reorder leave types; calls `PUT /api/admin/leave-types`.
- Employee list: `刪除` button rendered only when current user role is ADMIN. HR sees no button, no menu entry.

### 5.4 Export file format

CSV / Excel columns (in order, Chinese headers, Chinese values):

```
員工編號 | 姓名 | 部門 | 日期 | 班別時間 | 上班時間 | 下班時間 | 狀態 | 備註 | 遲到理由 | 送單狀態
```

Status value mapping (CSV / Excel only):
- `NORMAL` → `正常`
- `LATE` → `遲到`
- `EARLY_LEAVE` → `早退`
- `LATE_AND_EARLY_LEAVE` → `遲到且早退`
- `ABNORMAL` → `異常`
- `ABSENT` → `缺勤`
- `LEAVE` → `請假`

JSON: keys stay in `snake_case` English; status stays as enum string. JSON consumers (programmatic integrations) get the raw shape.

### 5.5 i18n keys

New keys in `frontend/src/messages/{en,zh}.json`:

```
status.leave
monthlyOverride.remark
monthlyOverride.leaveType
monthlyOverride.leaveTypeNone
monthlyOverride.submitMonth
monthlyOverride.warningTitle
monthlyOverride.warningBody
monthlyOverride.backToEdit
monthlyOverride.proceed
reports.shiftTime
reports.remark
reports.submissionStatus
reports.submitted
reports.unsubmitted
reports.includeUnsubmitted
admin.leaveTypes
admin.leaveTypesAdd
admin.leaveTypesRemove
```

## 6. Test Plan (TDD order)

### 6.1 Backend unit (~12 tests)

- `calculate_status(leave_type="特休", ...)` returns `LEAVE` regardless of clock-in/out timing.
- `calculate_status(leave_type=None, ...)` matches all existing test cases (regression guard).
- `monthly_submissions_repository` — upsert refreshes `submitted_at`; unique constraint enforced.
- `monthly_submissions_repository.list_by_month(year, month)` — returns one row per employee with `submitted_at | None`.

### 6.2 Backend integration (~13 tests)

- `POST /api/monthly-override` with `leave_type="特休"` → summary row has `status=LEAVE`, `leave_type="特休"`.
- `POST /api/monthly-override` with `remark="上午"` and no `leave_type` → summary status unchanged from punch-based calc.
- `POST /api/monthly-submissions` (self) → 200 + row created.
- `POST /api/monthly-submissions` (other emp_id, EMPLOYEE role) → 403.
- `POST /api/monthly-submissions` (other emp_id, HR role) → 200.
- Resubmission updates `submitted_at`.
- `GET /api/reports/daily` default (`submission_filter=submitted`) → excludes rows for unsubmitted (emp, year, month).
- `GET /api/reports/daily?submission_filter=all` → includes all rows.
- `GET /api/reports/daily?submission_filter=unsubmitted` → only unsubmitted rows.
- Non-HR caller sending `submission_filter=all` → behavior identical to `submitted` (silently forced).
- `GET /api/reports/export` default excludes unsubmitted; CSV headers are Chinese; status values are Chinese.
- `GET /api/reports/export?format=json` keeps English keys and enum values.
- `DELETE /api/employees/{id}` as HR → 403.
- `DELETE /api/employees/{id}` as ADMIN → 200 (existing 409 LSA guard still applies).
- `PUT /api/admin/leave-types` as HR → 200; as EMPLOYEE → 403.

### 6.3 Frontend unit (~10 tests)

- Warning modal triggers on each of LATE / EARLY_LEAVE / LATE_AND_EARLY_LEAVE / ABNORMAL / ABSENT.
- Warning modal does NOT trigger on LEAVE or NORMAL.
- Modal `返回修改` cancels save; `繼續送出` proceeds.
- `儲存全部` does not call `/api/monthly-submissions`; `本月送單` does.
- Reports page filter `送單狀態` correctly drives the `submission_filter` API param (all three values).
- `送單狀態` dropdown hidden for non-HR roles; API call always sends `submitted`.
- Admin employee-list `刪除` button hidden for HR.
- Leave-type dropdown sources options from `/api/admin/leave-types`.

### 6.4 Playwright E2E (1 new scenario)

Employee fills `特休` on a workday in monthly-override → saves → status becomes `請假` → clicks `本月送單` → confirms warning if any → HR opens `/reports` for that month → sees `已送單 ✓` for that employee.

### 6.5 Coverage target

Maintain ≥ 80% on both backend and frontend (CLAUDE.md requirement).

## 7. Migration & Backward Compatibility

### 7.1 Alembic migration

Single migration adds:
1. New enum value `LEAVE` on `attendancestatus` (`ALTER TYPE attendancestatus ADD VALUE 'LEAVE'`).
2. Two columns on `daily_attendance_summaries` (`leave_type`, `remark`), both NULL.
3. New table `monthly_submissions` with unique constraint and index.
4. Seed row in `system_config` for key `leave_types` (only if absent — idempotent).

Migration is forward-only. Downgrade path drops the columns/table; the enum value cannot be removed without rebuilding the type, so the downgrade leaves `LEAVE` in place as a no-op enum value.

### 7.2 Backward compatibility

- Existing summaries have `leave_type=NULL`, `remark=NULL` → `calculate_status` behavior is identical to today.
- Existing reports queries that don't pass `include_unsubmitted` would suddenly hide unsubmitted rows. Internal callers must be updated; there are no public/external consumers of these endpoints.
- `attendance_reasons` untouched — existing tardiness-reason flow continues working.
- HR users who relied on `DELETE /api/employees/{id}` get a 403; UI hides the button so the regression is invisible.

### 7.3 Rollout

Single deploy. No feature flag — the new columns default to NULL (inert) and the new endpoints are additive. The permission downgrade is the only breaking change for HR; covered by removing the UI button in the same release.

## 8. Open Risks

- **Enum migration on PostgreSQL** — `ALTER TYPE ... ADD VALUE` cannot run inside a transaction in older Postgres versions. Migration must use `op.execute("COMMIT")` or a non-transactional migration block. Validate target Postgres version during implementation.
- **`submission_filter` default flip** — any existing caller of `/api/reports/export` or `/api/reports/daily` will silently start returning fewer rows (only submitted). Audit usages before deploy. (Manual smoke checklist item.)
- **Memory reversal** — `project_hr_delete_permission.md` memory currently states HR holds delete; must be updated/removed when this lands.

## 9. References

- Meeting minutes 2026-05-13 (9-item list).
- Brainstorming Q1–Q5 transcript (2026-05-13 to 2026-05-14 session).
- CLAUDE.md decisions #18 (AttendanceStatus enum), #20/#23 (Monthly Punch Override), #21 (Team page reason column), #17 (Departments), #14 (Grace period).
- Existing specs: `2026-04-10-monthly-punch-override-design.md`, `2026-04-10-absent-status-design.md`.
