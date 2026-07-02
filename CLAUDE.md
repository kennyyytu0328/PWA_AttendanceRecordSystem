# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# GoGoFresh Attendance Record System

## Project Overview

Zero-Trust PWA Attendance System for hybrid work (office + WFH). Replaces physical punch clocks with biometric-bound, location-verified digital attendance.

## Tech Stack

- **Frontend**: Next.js (App Router), React, TailwindCSS, `next-pwa`
- **Backend**: Python FastAPI
- **Database**: PostgreSQL (SQLAlchemy/SQLModel)
- **Auth**: WebAuthn/FIDO2 (`webauthn` backend, `@simplewebauthn/browser` frontend), JWT via `python-jose`
- **Geospatial**: Haversine Formula (2km threshold, configurable office location via DB)
- **Testing**: pytest + pytest-asyncio (backend), vitest + testing-library + Playwright (frontend)
- **Container**: Docker Compose (PostgreSQL, backend, frontend)

## Architecture

### Database Tables

| Table | Purpose |
|-------|---------|
| `employees` | Employee records with role (EMPLOYEE/MANAGER/HR/ADMIN) |
| `authenticators` | WebAuthn credentials bound to employees |
| `attendance_logs` | Immutable event-sourced punch records |
| `system_config` | Configurable settings (e.g., office location) as JSONB |
| `daily_attendance_summaries` | Computed First-In-Last-Out daily reports |
| `attendance_reasons` | Employee-submitted reasons for LATE/EARLY_LEAVE |

### Role Permissions

| Role | Permissions |
|------|------------|
| `EMPLOYEE` | Clock in/out, view own attendance |
| `MANAGER` | + View team attendance, approve overrides |
| `HR` | + Manage employees, view all attendance, change office location, export reports |
| `ADMIN` | + Full system access, role management, system config |

### Backend Structure (Layered)

```
backend/app/
  models/        — SQLAlchemy/SQLModel ORM models
  schemas/       — Pydantic request/response validation
  repositories/  — Data access layer (Repository pattern)
  services/      — Business logic layer
  routers/       — FastAPI route handlers
  middleware/    — Auth (JWT), rate limiting
  utils/         — Pure utilities (haversine, password hashing)
```

### Frontend Structure

```
frontend/src/
  app/           — Next.js App Router pages (login, punch, dashboard, admin, reports, attendance, team)
  components/    — Reusable UI components
  hooks/         — Custom hooks (useGeolocation, useWebAuthn, useAttendance)
  lib/           — API client, auth context, validators
  messages/      — i18n translation files (en.json, zh.json)
  types/         — TypeScript interfaces
```

## Core Design Decisions

1. **Immutable attendance logs** — No UPDATE on `attendance_logs`. Overrides create new entries with `is_overridden=True`. Repository has no update/delete methods.
2. **Office location from DB** — Never hardcoded. Read from `system_config` table (`office_location` key). Geolocation service reads it at punch time.
3. **First-In-Last-Out reporting** — MIN(timestamp) = clock-in, MAX(timestamp) = clock-out. Configurable grace period (default 5 min, stored in `system_config` table). Both LATE and EARLY_LEAVE are tracked independently — if both occur, status is `LATE_AND_EARLY_LEAVE`.
4. **No external SSO** — Employee ID + Password for onboarding; WebAuthn for daily use. No user enumeration (same error for wrong password and user not found).
5. **Event sourcing** — All punches recorded with full metadata (GPS, accuracy, IP, work_mode).
6. **Permission hierarchy** — ADMIN > HR > MANAGER > EMPLOYEE. Declarative frozenset-based permission matrix in `permission_service.py`.
7. **WebAuthn clone detection** — Sign count monotonicity enforced for *counting* authenticators. A regression (non-zero `new_sign_count <= stored`) raises ValueError. **Exception (WebAuthn L2 §6.1.1):** a `new_sign_count` of 0 means the authenticator implements no counter — the norm for synced passkeys (Google Password Manager on Android) — so 0 is accepted, never flagged, and never lowers the stored high-water mark (see `webauthn_service.verify_authentication`). The stored count only ever advances (`new > stored`).
8. **WorkMode enum values** — Backend uses `OFFICE` / `WFH` (not `WFO`). Frontend `WorkMode` type must match: `"OFFICE" | "WFH"`.
9. **Date range queries** — Team logs, all logs, history, and reports endpoints use `start_date`/`end_date` parameters (not single `date`). Frontend pages include date range pickers.
10. **WebAuthn credential ID encoding** — All credential IDs must use consistent base64url encoding throughout registration, storage, and authentication flows. The `loginWithToken` method in AuthContext handles token-based login after WebAuthn authentication.
11. **i18n support** — Frontend uses `next-intl` with translation files in `frontend/src/messages/` (en.json, zh.json). All user-facing strings should use translation keys.
12. **Tardiness detection at punch time** — Punch response includes `tardiness_status` (LATE/EARLY_LEAVE/LATE_AND_EARLY_LEAVE/null) and `summary_id`. Auto-generates daily summary when tardy so employee can immediately submit a reason. Frontend checks if reason already submitted before showing form.
13. **Attendance reasons** — Separate `attendance_reasons` table (one reason per summary). Employee submits reason via `POST /api/reasons` when LATE, EARLY_LEAVE, or LATE_AND_EARLY_LEAVE. Respects immutability (no mutation of attendance logs).
14. **Configurable grace period** — Stored in `system_config` table (key `grace_period`, value `{"minutes": N}`). HR+ can update via admin UI. Default: 5 minutes.
15. **Export formats** — CSV, JSON, and Excel (.xlsx via openpyxl). Supports filtering by department and/or individual `emp_id`.
16. **Single punch = clock-in** — A single punch is always treated as a clock-in. If it's past the grace deadline, status is LATE; if on time, status is NORMAL (not ABNORMAL). If an employee forgot to clock in earlier, the manager override flow covers that case. The summary is regenerated when the second punch (clock-out) arrives. **Single-punch display**: because First-In-Last-Out collapses one punch to `first_clock_in == last_clock_out`, summary-based views must NOT echo that timestamp as a clock-out (it looks like an instant early-leave). The monthly-override page (`isSinglePunch(summary)`) renders the clock-out **blank**, and the reports page (`isSinglePunch(first, last)`) renders it as 「無紀錄」/no-record. Status is unaffected (stays LATE/NORMAL per the rule above). Event-level views (team, attendance history) list raw punch rows, so they're unaffected. Export intentionally still emits the raw value.
17. **Department management** — Pre-set departments stored in `system_config` table (key `departments`). HR+ manages via admin UI. Employee create/edit forms use dropdown (not free text).
18. **AttendanceStatus enum** — 5 values: `NORMAL`, `LATE`, `EARLY_LEAVE`, `LATE_AND_EARLY_LEAVE`, `ABNORMAL`. All status pages (attendance history, team, reports) display localized status badges. Shift time validation rejects `shift_end_time <= shift_start_time`.
19. **ABSENT status for no-punch workdays** — When ADMIN triggers `POST /api/reports/generate` for a date, `generate_all_summaries()` creates `ABSENT` summaries for every employee with no punches *if* that date is a workday per the cached Taiwan calendar (falling back to Mon-Fri when no calendar data is cached). Holidays, weekends, and 補班 non-workdays never generate ABSENT summaries. ABSENT rows have `first_clock_in=NULL` and `last_clock_out=NULL`. HR fixes false ABSENTs via Monthly Punch Override, which upserts the summary to the calculated status (NORMAL/LATE/etc).
20. **Monthly punch override** — Employees can bulk-edit their first clock-in and last clock-out times for any day of the month via a dashboard quick action. Overrides take effect immediately (no approval workflow). Original raw punch records in `attendance_logs` are preserved for HR/Manager audit. Employees can also pre-fill clock-in/clock-out for future days (end-of-month salary settlement). Overrides create new entries in `attendance_logs` with `is_overridden=True`; daily summaries are recalculated after each save.
21. **Team page reason column** — `/api/reports/daily` includes `reason` field (joined from `attendance_reasons`). Team page displays reason text next to status for HR/Manager review.
22. **Taiwan workday calendar** — Auto-fetched from ruyut/TaiwanCalendar CDN (sourced from 行政院人事行政總處), cached in `system_config` table (key `workday_calendar_{year}`). Falls back to Mon-Fri if fetch fails. HR can manually refresh via admin panel ("更新全年行事曆"). Used by monthly override page. Distinguishes workdays, holidays, weekends, and 補班 (make-up workdays).
23. **Monthly punch override** — Employees bulk-edit clock-in/clock-out for any workday of a month via `/dashboard/monthly-override`. HR+ can override any employee (with department filter + employee selector). Overrides mark old logs as `is_overridden=True`, create new logs, and recalculate daily summaries. No approval workflow. Supports pre-filling future days for salary settlement.
24. **LAN dev access** — Frontend `next.config.ts` uses `allowedDevOrigins: ["192.168.2.*"]` (DNS-segment wildcard, NOT CIDR — Next.js splits on `.`). Backend `config.py` has `cors_origin_regex: r"http://192\.168\.\d+\.\d+:3000"` (regex matching any LAN IP). Remove both in production.
25. **Production deployment** — `docker-compose.prod.yml` + `frontend/Dockerfile.prod` (multi-stage, non-root, `npm start`) + `backend/.env.production.example` + `frontend/.env.production.example` templates. Full walkthrough in `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`. Key constraints: `NEXT_PUBLIC_API_URL` is baked in at build time (requires rebuild to change); WebAuthn requires HTTPS + bare-host `RP_ID` equal to the production domain; `seed.py` must NOT be run in prod (ships weak test passwords). **PostgreSQL runs as the bundled `db` service** (`postgres:16-alpine`, `pgdata` volume, no published port) — the production server (`go2fresh-1`) is Ubuntu 18.04 whose apt tops out at PG 10, so host Postgres is not an option there. `POSTGRES_PASSWORD` in the root `.env` must equal the password inside `backend/.env` `DATABASE_URL` (host `db:5432`), and is only applied on the volume's first start. A host-Postgres alternative (used by the original alg-compute-0 deployment) stays documented in a comment block at the bottom of the compose file.
26. **Soft-delete for terminated employees** — `employees.terminated_at` (nullable timestamp) marks resigned employees. Required by Taiwan Labor Standards Act §30(5), which mandates attendance-record retention (5 years minimum). Hard `DELETE /api/employees/{id}` is rejected with 409 when attendance_logs reference the employee; HR must use `POST /api/employees/{id}/terminate` instead (reversible via `/reactivate`). Terminated employees are blocked from password and WebAuthn login (same generic "Invalid credentials" error to avoid enumeration). `GET /api/employees` excludes terminated by default; pass `?include_terminated=true` for HR audit views. Never self-terminate (blocked at API and UI). Reports (`/api/reports/daily`, `/api/reports/export`) also accept `include_terminated`: when an explicit `emp_id` is specified it is always honored regardless of termination (LSA retention takes priority); without `emp_id`, terminated employees are hidden unless `include_terminated=true`. `generate_all_summaries` iterates all employees (so historical summaries for resigned employees are always returned), but skips ABSENT generation for employees already terminated on/before the target date. Only the Reports page surfaces the "Include resigned employees" toggle (HR+) — Monthly Override intentionally does not.
27. **Sub-path production deployment via upstream proxy** — In production the app is fronted by an external reverse proxy at `https://www.gogoffcc.com/gogoffcc-arms` that we don't control (TLS terminates upstream). The upstream forwards `/gogoffcc-arms/*` unchanged to our server's host nginx, which **strips** the prefix for BOTH layers: `/gogoffcc-arms/api/` → `127.0.0.1:8120/api/` (FastAPI sees `/api/...`) and `/gogoffcc-arms/` → `127.0.0.1:3000/` (Next.js 16 serves routes at unprefixed paths — its `basePath` only affects URL/asset *generation* in the bundle, a behavior change from ≤15 where the prefix had to be preserved). Every path-prefix knob is env-driven so dev stays unchanged: frontend `NEXT_PUBLIC_BASE_PATH` (defaults to `""`) feeds `next.config.ts` `basePath` and the dynamic `src/app/manifest.ts`; backend `ROOT_PATH` (defaults to `""`) feeds FastAPI `root_path`. uvicorn runs with `--proxy-headers --forwarded-allow-ips=*` so `X-Forwarded-Proto: https` is honored (otherwise WebAuthn rejects all biometric logins as non-HTTPS). The PWA manifest is now a dynamic Next.js route at `app/manifest.ts` (not a static `public/manifest.json`) so `start_url`/`scope`/icon paths automatically include the basePath. The browser favicon lives at `frontend/src/app/icon.png` (64×64 GOGO logo derived from `public/icons/icon-1024.jpg`); no `public/favicon.ico` to avoid implicit-fallback conflicts. WebAuthn `RP_ID=www.gogoffcc.com` and `expected_origin=https://www.gogoffcc.com` — neither value ever includes the `/gogoffcc-arms` path. See `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §6 Option C for the upstream Nginx config and §7.1 for the post-deployment smoke checklist.
28. **`find_first_clock_in` / `find_last_clock_out` must exclude overridden rows** — Both repository helpers (`backend/app/repositories/attendance_repository.py`) filter `is_overridden == False` in their `WHERE` clause. Without this filter, a stale overridden log can win the MIN/MAX comparison by timestamp alone and contaminate `generate_daily_summary` — a regression that surfaced as "save 17:25 clock-out → reload shows 20:25" when a previously-overridden 20:25 row still had the largest timestamp for the day. Any future query that needs "current punch state" (not audit history) must apply the same filter. Audit/reporting views that want to see the full history should call a separate function — do not weaken these two.

29. **JWT revocation via `password_changed_at`** — On successful `POST /api/auth/change-password`, the employee's `password_changed_at` is set to `now(UTC)`. The auth middleware (`get_current_user` in `backend/app/middleware/auth_middleware.py`) rejects any decoded JWT whose `iat` predates that timestamp. Tokens without an `iat` claim (issued before this feature) and employees with `password_changed_at IS NULL` skip the check, preserving backward compatibility. JWT issuance sets `iat` in both paths: `employee_service.authenticate` (password login) and `routers/auth.py::authenticate_verify` (WebAuthn login). When a database row returns `password_changed_at` as a tz-naive datetime, it is normalized to UTC-aware before comparison (defensive against driver edge cases).

31. **休息日 / 例假日 + overtime_hours** — Labor-law-aligned weekend semantics + structured overtime field. (a) New `DayKind` classification surfaced via `/api/config/workdays` (`day_kind`): `WORKDAY` / `MAKEUP_WORKDAY` / `NATIONAL_HOLIDAY` / `REST_DAY` (週六) / `REGULAR_LEAVE` (週日). Sunday always classifies as `REGULAR_LEAVE` — labor-law-mandated weekly rest takes priority even over a national holiday falling on Sunday. (b) **Editability matrix**: Sunday is locked for **everyone including ADMIN** (both live punch and bulk override are rejected — `POST /api/attendance/punch` returns 400 via `ValueError`, `PUT /api/attendance/override-bulk` raises `PermissionError` mapped to 403); Saturday is locked for live punching for all roles and writable in override only when requester role is HR or ADMIN; 補班 Saturday (`is_makeup_workday=true`) bypasses both locks and behaves like a regular workday. Weekday national holidays remain non-editable (unchanged from prior behavior). (c) **`overtime_hours` column** (`NUMERIC(3,1)` on `daily_attendance_summaries`) — independent of `leave_type`, can coexist (e.g. half-day leave + 4hr OT). Validation: `>= 1.0` and a multiple of 0.5 (first hour is whole; subsequent hours in 0.5 increments). Enforced at the Pydantic schema layer (`BulkOverrideEntry.overtime_hours` field_validator) and by a DB `CHECK` constraint (`ck_summary_overtime_hours_step`). `upsert_summary` uses a `_UNSET` sentinel so existing callers (punch / summary recompute) leave the persisted value alone; `generate_daily_summary` reads and round-trips `overtime_hours` like it does `leave_type`/`remark`. Excel/CSV export adds 「加班時數」column and uses new STATUS_ZH labels (`REST_DAY`→「休息日」, `REGULAR_LEAVE`→「例假日」, `NATIONAL_HOLIDAY`→「國定假日」) — old `HOLIDAY`/`WEEKEND` keys kept in the map for backward-compat. The reporting service's filler-row classifier was rewritten to use `classify_day_kind` so weekend rows distinguish 休息日 vs 例假日 instead of collapsing both to「週末」. Frontend monthly-override and punch pages consume `day_kind` from the workdays endpoint with a `deriveDayKind` weekday fallback if an older backend omits the field; the punch page seeds its day_kind from a local weekday guess so the button disables immediately on weekends, then upgrades to the calendar-authoritative answer (lets 補班 Saturday re-enable the button). (d) **`overtime_hours` is never dropped on read** — `generate_daily_summary` previously returned `None` (discarding the summary) whenever `calculate_status` returned `None` (no punch + no leave). That silently lost overtime entered on a no-punch day, and on non-workdays the row was never re-emitted (`generate_all_summaries` skips the ABSENT fallback off-workday), so 休息日加班 vanished on reload. Fix: when `status is None` but `existing_overtime_hours is not None`, preserve the row (keep the existing ABSENT placeholder status) and round-trip the value instead of returning `None`. (e) **Overtime requires both punch times (frontend save-block)** — overtime implies actual work, so the monthly-override page treats any editable row with `overtime_hours` set but a missing clock-in *or* clock-out as a data-entry error: `rowNeedsPunchForOvertime` drives an inline red cue (row highlight + red-bordered punch input + ⚠ icon next to the OT selector) and `handleSave` hard-blocks (opens `OvertimePunchModal` listing the offending dates and aborts the PUT — no "proceed anyway"). The block scans **all** editable rows, so legacy no-punch overtime rows resurfaced by (d) are flagged and must be corrected before any save. This is frontend-only — the `override-bulk` endpoint does not yet enforce it server-side (deferred to avoid conflicting with the half-day-leave + OT coexistence case). The OT dropdown caps at 6h (`1, 1.5, … 6`). (f) **Non-working-day punches are NORMAL, never LATE/EARLY_LEAVE** — there is no scheduled shift on a 休息日 / 例假日 / 國定假日, so weekend/holiday overtime work must not be scored against weekday shift times. `calculate_status` takes a `day_kind` parameter and short-circuits to `NORMAL` (after the no-punch→`None` check, before the ABNORMAL/late/early branches) when `day_kind ∈ {REST_DAY, REGULAR_LEAVE, NATIONAL_HOLIDAY}` (`_NON_WORKING_DAY_KINDS`). `generate_daily_summary` gained an optional `day_kind` param: hot paths pass the calendar-accurate value (`generate_all_summaries` loads the calendar once and classifies before the per-employee loop; `bulk_override` reuses its per-entry gate `day_kind`; the live-punch flow passes its already-computed `day_kind`), while standalone/test callers fall back to a pure `_weekday_fallback(date)` (Sat→REST_DAY, Sun→REGULAR_LEAVE) so no DB/CDN hit occurs. Existing `LATE_AND_EARLY_LEAVE` weekend summaries self-heal to `NORMAL` on the next read because `get_daily_report`→`generate_all_summaries` recomputes and upserts. (g) **Export columns: 星期 + 休息日加班 annotation** — CSV/Excel now include a 星期 column (星期一…星期日 via `_weekday_zh`, inserted right after 日期; all column indices after 日期 shifted +1). For a real summary row on a non-makeup non-working day **with work** (a punch or recorded overtime), the 備註 column is prefixed with a labor-law label via `_annotate_overtime_remark` (`_OVERTIME_REMARK_ZH`: REST_DAY→「休息日加班」, NATIONAL_HOLIDAY→「國定假日加班」, REGULAR_LEAVE→「例假日加班」), combined with any employee remark using `·` (e.g.「休息日加班·盤點」). Day-kind is classified from a calendar preloaded once before the row-build loop (shared with the filler-row logic). No-work weekend filler rows keep showing the day description only. The on-screen reports page (`/api/reports/daily`) is unchanged — annotation is export-only; export is intentionally the last workflow step (employees verify punch times via the monthly-override save-block before 本月送單, then HR exports).

30. **Leave-type + remark + monthly submission** — Three companion features on `daily_attendance_summaries` (the `attendance_reasons` table stays independent — different purpose). (a) `AttendanceStatus.LEAVE` added; `calculate_status` short-circuits to `LEAVE` whenever `leave_type` is non-null, taking priority over LATE/EARLY_LEAVE/ABSENT. (b) `leave_type` (max 50) and `remark` (max 500) columns persisted on every summary; bulk-override and reports endpoints round-trip both fields. Configured leave-type list lives in `system_config` under key `leave_types` and is managed via `/api/admin/leave-types` (GET any auth, PUT HR+). (c) New `monthly_submissions` table with `UNIQUE(emp_id, year, month)` records that an employee has "filed" the month. **Submission is informational, not a lock** — `PUT /api/attendance/override-bulk` deliberately does not check the submission table, so an employee or HR can keep editing a submitted month. Intentional: real-world edge cases (e.g. a same-day leave reported on the last day of the month) need to be editable after submission. There is no unsubmit/withdraw endpoint because there is nothing to unlock. The "submitted" state only gates `submission_filter` on `/api/reports/daily` and `/api/reports/export`. `POST /api/monthly-submissions` is self-or-HR+; the frontend "本月送單" button scans for abnormal days (LATE/EARLY_LEAVE/LATE_AND_EARLY_LEAVE/ABSENT) and pops a **month-level** `WarningModal` listing them before sending — user can "返回修改" or "繼續送出". (d) `/api/reports/daily` and `/api/reports/export` accept `submission_filter=submitted|unsubmitted|all`. The backend validates the value (unknown → `submitted`) but does **not** force-override by role — Managers need `all` for daily team monitoring on the team page (`/team` passes `submission_filter=all`). Visibility on the reports page is UI-gated: only HR/ADMIN see the toggle there. Employees never reach these endpoints (MANAGER+ required). The monthly-override editor (`GET /api/attendance/summaries`) always passes `submission_filter=all` and now returns `leave_type`/`remark` so the page can pre-populate before submission. Export columns use Chinese headers and include `shift_time`, `remark`, `reason`, and `submission_status`. (e) **DELETE permission moved from HR to ADMIN only** (`require_role(Role.ADMIN)` on `DELETE /api/employees/{id}`) — reverses the prior HR-can-delete decision. HR retains terminate/reactivate. The admin-page Delete button is gated behind `user.role === "ADMIN"`.

32. **Org reporting hierarchy (`reports_to` + `rank`) + subtree-scoped manager authority** — Phase 15. (a) Two new nullable `employees` columns (migration `b8c9d0e1f2a3`): `reports_to` (an `emp_id` — the org-chart parent) and `rank` (free-text title label). **`rank` grants NO permissions** — it is display-only; authority is always the `role` enum (EMPLOYEE/MANAGER/HR/ADMIN). Ranks are a configurable ordered list (most-senior first) in `system_config` key `ranks`, default `["PRESIDENT", "VP", "AVP", "MANAGER"]` (`get_ranks` returns this default when unset — unlike departments/leave_types which default empty), managed via `/api/admin/ranks` (GET any auth, PUT HR+), UI = `RanksTab`. (b) **Authority scope** lives in `app/middleware/scope.py::resolve_scope` → frozen `Scope` (this answers *which employees* a caller may act on, distinct from `permission_service`'s *what actions*): HR/ADMIN = company-wide; MANAGER = own reporting subtree (root-inclusive recursive `reports_to` walk via `employee_repository.get_subtree_emp_ids`, which uses `UNION` not `UNION ALL` so a malformed cycle still terminates); EMPLOYEE = self only. (c) **Gated by the `org_scoping_enabled` flag** (`system_config`, **default OFF**). While OFF, *everyone* resolves company-wide to preserve pre-feature behavior — so `/api/attendance/team` falls back to the **legacy department-scoped** `get_team_logs` (a manager sees only their own department, NOT the reporting tree), and `reports_to`/`rank` are effectively inert. Flip it **ON** (ADMIN-only, via `OrgScopingSection` / `PUT /api/admin/org-scoping`) to activate subtree visibility. Asymmetric gating is intentional: the scoping toggle is ADMIN-only, but the ranks list is HR+. (d) Subtree scoping is enforced on the **4 manager-facing endpoints** — `/api/attendance/team`, `PUT /api/attendance/override-bulk`, `/api/reports/daily`, `/api/reasons` — each calls `resolve_scope` and filters by `scope.can_see(...)`; the team endpoint additionally switches between `get_team_logs` (company-wide) and `get_logs_for_emp_ids(scope.visible_emp_ids)` (scoped). (e) **`reports_to` write guard** (`employee_service._validate_reports_to`) rejects self-reference, unknown manager, and cycle-creating edges (target already inside the employee's subtree). It raises `InvalidReportsToError`, which carries a stable machine-readable `code` (`reports_to_self` / `reports_to_not_found` / `reports_to_cycle`); the router maps it to HTTP 400 with `detail={"code", "message"}` — the project's first **structured-detail** error, so the frontend can localize via `errReportsTo*` i18n keys instead of showing raw English. `ApiError` + `api.ts request()` handle object-shaped `detail` while staying backward-compatible with all existing string details. (f) i18n: the `MANAGER` **role** label is zh「管理層」(a permission tier), deliberately distinct from the **rank**「經理」(a job title below AVP) — never conflate role and rank in UI copy.

33. **WebAuthn challenges persisted in PostgreSQL (worker-safe)** — The WebAuthn ceremony is two requests (`/authenticate/generate-options` → `/authenticate/verify`; same shape for registration). The challenge was previously held in a per-process in-memory dict (`webauthn_service._challenges`), so under `uvicorn --workers N` the verify request only succeeded when it happened to hit the same worker that generated the challenge (≈1/N). This surfaced as **intermittent** "No pending authentication challenge" login failures — on Android, fingerprint login succeeding only ~1 in 3–4 attempts at `--workers 4`. Challenges now live in the `webauthn_challenges` table (`emp_id` PK + FK→`employees` ON DELETE CASCADE, `challenge` base64url, `created_at` tz-aware), accessed via `webauthn_challenge_repository.set_challenge` / `consume_challenge`. Two properties: **single-use** (deleted on consume — a failed verify needs a fresh generate, which the frontend `useWebAuthn` flow already issues per attempt) and **TTL-bounded** (`CHALLENGE_TTL_SECONDS = 300`; expired rows are still deleted on read, tz-naive `created_at` normalized to UTC before comparison). `generate_*_options` upsert (one pending challenge per `emp_id`); the router consumes on verify, keeping the `None → 400` guard. The `verify_registration` / `verify_authentication` service functions still take an explicit `challenge: bytes` (pure verification). This restores `docker-compose.prod.yml --workers 4` — **never reintroduce a process-local challenge store**. Requires `alembic upgrade head` (migration `c9d0e1f2a3b4`).

34. **Containers must run in Asia/Taipei time (TZ + tzdata)** — The app implicitly assumes *server-local time == Taiwan time*. Live punches are stamped with **naive** `datetime.datetime.now()` (`attendance_service.py`, the live-punch and resubmit paths), tardiness is judged by comparing `log.timestamp.time()` against the employee's Taiwan wall-clock `shift_start_time` / `shift_end_time`, and `attendance_logs.timestamp` is a `TIMESTAMP WITHOUT TIME ZONE` column (`sa.DateTime`, no `timezone=True`) serialized to JSON **without** a `Z`/offset suffix. Docker containers default to **UTC**, so on a UTC host every live punch lands −8h: an 08:53 punch is stored as naive `00:53`, the frontend `new Date("...T00:53:00")` (e.g. `monthly-override` `extractTime`) reads it as local 00:53, and tardiness is mis-scored. Fix is **environmental, not code**: `docker-compose.prod.yml` pins `TZ: Asia/Taipei` on all three services and `backend/Dockerfile` installs `tzdata` (the `python:3.13-slim` base ships none, so without it glibc silently ignores `TZ` and stays UTC). Verify after deploy with `docker compose exec backend date` → must show `CST` / `+0800`. **Local Windows dev already runs in Taiwan time, which is why this only ever manifested in prod.** Manually *overridden* times are unaffected (bulk-override uses `datetime.combine(date, user_typed_time)`, no `now()`), so a tell-tale symptom is "live punches off by 8h,補登 times correct". Pre-fix rows are **not** retroactively corrected — they must be fixed per-day via Monthly Punch Override (summaries/status self-heal on next read). See `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §4.1. A future fully-tz-aware refactor (UTC-aware columns + frontend conversion) would also have to migrate the shift-time comparison logic — deferred as higher-risk.

35. **NFC door-tap gap-fill backup (deployed 2026-07-03)** — SOYAL 701 door-tap exports (`YYYYMM.txt`, CP950) act as a **backup source** for missing phone/WebAuthn punches. The office door PC (`DESKTOP-MMGK6PJ`, behind NAT/DHCP) **pushes** the file daily at 00:20 via Task Scheduler (`GoGoFresh NFC Push`, `/RU SYSTEM`) to `POST /api/nfc/import` with header `X-NFC-API-Key` (backend env `NFC_IMPORT_API_KEY`; on the door PC it's a machine-level env var). Pull was impossible (inbound to LAN blocked). Per `(emp_id, date)`: earliest tap = clock-in candidate, latest = clock-out candidate (`door_no` is ignored — it's a door number, not in/out); a **real phone punch always wins** — NFC only fills the missing side, and a filled side is never re-filled (idempotent). NFC-created logs carry `ip_address="nfc"` (no DB migration). Taps on weekends/holidays are recorded and scored NORMAL via `day_kind` (#31f). Unknown emp_ids and terminated employees are skipped and reported, never fail the batch. On the 1st of the month the agent also resends last month's file. Door-side agent lives in `tools/nfc-agent/` (`push-nfc.ps1` must stay **UTF-8 with BOM** — the Chinese SOYAL folder path breaks on PS 5.1 without it) and ships curl.se's curl next to it because the production edge is TLS 1.3-only and Windows 10 schannel tops out at TLS 1.2. As-built install: `C:\Users\ltre5\nfc-agent\` — full runbook incl. SSH remote management (PuTTY plink/pscp with pinned hostkey; plain OpenSSH can't script the password and plink without `-hostkey` hangs) in `tools/nfc-agent/README.md`. Design spec: `docs/superpowers/specs/2026-07-01-nfc-punch-backup-design.md`.

## Development Methodology

**TDD (Test-Driven Development)** — Strict RED-GREEN-IMPROVE cycle for every feature:
1. Write failing tests first (RED)
2. Write minimal implementation to pass (GREEN)
3. Refactor while keeping tests green (IMPROVE)

**Coverage target**: 80%+ on both frontend and backend.

## Coding Conventions

### Python (Backend)

- Async everywhere (async def, await)
- Type hints on all function signatures
- Pydantic for all input validation
- Repository pattern for data access (no direct DB queries in services/routers)
- Immutable patterns — return new objects, don't mutate
- Repository functions are module-level async functions (not classes), taking `session: AsyncSession` as first param
- Use `datetime.datetime.now(datetime.UTC)` (not deprecated `utcnow()`)
- Frozen dataclasses for service result types (e.g., `WorkModeResult`, `PunchResult`)

### TypeScript (Frontend)

- Strict TypeScript (`strict: true`)
- Zod for runtime validation
- Custom hooks for side effects (geolocation, WebAuthn)
- TailwindCSS for styling (no CSS modules)
- Lucide React for icons, Framer Motion for animations

### General

- No `console.log` in production code
- No hardcoded secrets — use environment variables
- Functions < 50 lines, files < 800 lines
- Error handling on all async operations
- Parameterized queries only (no string interpolation in SQL)

## Commands

### Backend

```bash
cd backend
pytest                          # Run all tests
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests only
pytest --cov=app --cov-report=term-missing  # Coverage report
uvicorn app.main:app --reload   # Dev server
alembic upgrade head            # Run migrations
alembic revision --autogenerate -m "description"  # Create migration
```

### Frontend

```bash
cd frontend
npm run dev                     # Dev server
npm run build                   # Production build
npx vitest run                  # Run unit tests
npx vitest run --coverage       # Coverage report
npx playwright test             # E2E tests
```

### Docker

```bash
# Development
docker-compose up -d            # Start all services
docker-compose down             # Stop all services
docker-compose up db            # Start PostgreSQL only

# Production (see docs/PRODUCTION_DEPLOYMENT_GUIDE.md)
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

## Implementation Phases

See `TODO.md` for detailed progress tracking.

| Phase | Scope | Tests | Status |
|-------|-------|-------|--------|
| 0 | Project Scaffolding & Test Infrastructure | 2 smoke | Done |
| 1 | Database Models & Core Utilities | 31 | Done |
| 2 | Repository Layer (Data Access) | 33 | Done |
| 3 | Service Layer (Business Logic) | 64 | Done |
| 4 | API Layer (Routers) | 60 | Done |
| 5 | Frontend Core Infrastructure | 27 | Done |
| 6 | Frontend Feature Pages | 33 | Done |
| 7 | End-to-End Tests | 5 + 33 stubs | Done |
| 8 | Security Hardening & Final Polish | 31 | Done |
| 9 | Bug Fixes & Enhancements (Date Range, WebAuthn Frontend, Navigation) | — | Done |
| 10 | Meeting Requirements (Tardiness, Reasons, Grace Period, Export) | — | Done |
| 11 | Bug Fixes & Admin Enhancements (Departments, Location Display, Status Fixes) | — | Done |
| 12 | Absent Status Tracking (Taiwan calendar integration) | 6 | Done |
| 13 | Monthly Punch Override & Team Reason Column | 44 | Done |
| 14 | UX Enhancements | — | In Progress |
| 15 | Org Reporting Hierarchy (reports_to, rank, subtree-scoped authority, org-scoping toggle) | — | Done |

**Current test count: 431 backend + 149 frontend = 580 passing + 33 Playwright E2E stubs** (1 pre-existing frontend flake in `monthly-override/page.test.tsx` — a `waitFor` timeout, unrelated to current work)
