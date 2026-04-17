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
7. **WebAuthn clone detection** — Sign count monotonicity enforced. Regression raises ValueError.
8. **WorkMode enum values** — Backend uses `OFFICE` / `WFH` (not `WFO`). Frontend `WorkMode` type must match: `"OFFICE" | "WFH"`.
9. **Date range queries** — Team logs, all logs, history, and reports endpoints use `start_date`/`end_date` parameters (not single `date`). Frontend pages include date range pickers.
10. **WebAuthn credential ID encoding** — All credential IDs must use consistent base64url encoding throughout registration, storage, and authentication flows. The `loginWithToken` method in AuthContext handles token-based login after WebAuthn authentication.
11. **i18n support** — Frontend uses `next-intl` with translation files in `frontend/src/messages/` (en.json, zh.json). All user-facing strings should use translation keys.
12. **Tardiness detection at punch time** — Punch response includes `tardiness_status` (LATE/EARLY_LEAVE/LATE_AND_EARLY_LEAVE/null) and `summary_id`. Auto-generates daily summary when tardy so employee can immediately submit a reason. Frontend checks if reason already submitted before showing form.
13. **Attendance reasons** — Separate `attendance_reasons` table (one reason per summary). Employee submits reason via `POST /api/reasons` when LATE, EARLY_LEAVE, or LATE_AND_EARLY_LEAVE. Respects immutability (no mutation of attendance logs).
14. **Configurable grace period** — Stored in `system_config` table (key `grace_period`, value `{"minutes": N}`). HR+ can update via admin UI. Default: 5 minutes.
15. **Export formats** — CSV, JSON, and Excel (.xlsx via openpyxl). Supports filtering by department and/or individual `emp_id`.
16. **Single punch = clock-in** — A single punch is always treated as a clock-in. If it's past the grace deadline, status is LATE; if on time, status is NORMAL (not ABNORMAL). If an employee forgot to clock in earlier, the manager override flow covers that case. The summary is regenerated when the second punch (clock-out) arrives.
17. **Department management** — Pre-set departments stored in `system_config` table (key `departments`). HR+ manages via admin UI. Employee create/edit forms use dropdown (not free text).
18. **AttendanceStatus enum** — 5 values: `NORMAL`, `LATE`, `EARLY_LEAVE`, `LATE_AND_EARLY_LEAVE`, `ABNORMAL`. All status pages (attendance history, team, reports) display localized status badges. Shift time validation rejects `shift_end_time <= shift_start_time`.
19. **ABSENT status for no-punch workdays** — When ADMIN triggers `POST /api/reports/generate` for a date, `generate_all_summaries()` creates `ABSENT` summaries for every employee with no punches *if* that date is a workday per the cached Taiwan calendar (falling back to Mon-Fri when no calendar data is cached). Holidays, weekends, and 補班 non-workdays never generate ABSENT summaries. ABSENT rows have `first_clock_in=NULL` and `last_clock_out=NULL`. HR fixes false ABSENTs via Monthly Punch Override, which upserts the summary to the calculated status (NORMAL/LATE/etc).
20. **Monthly punch override** — Employees can bulk-edit their first clock-in and last clock-out times for any day of the month via a dashboard quick action. Overrides take effect immediately (no approval workflow). Original raw punch records in `attendance_logs` are preserved for HR/Manager audit. Employees can also pre-fill clock-in/clock-out for future days (end-of-month salary settlement). Overrides create new entries in `attendance_logs` with `is_overridden=True`; daily summaries are recalculated after each save.
21. **Team page reason column** — `/api/reports/daily` includes `reason` field (joined from `attendance_reasons`). Team page displays reason text next to status for HR/Manager review.
22. **Taiwan workday calendar** — Auto-fetched from ruyut/TaiwanCalendar CDN (sourced from 行政院人事行政總處), cached in `system_config` table (key `workday_calendar_{year}`). Falls back to Mon-Fri if fetch fails. HR can manually refresh via admin panel ("更新全年行事曆"). Used by monthly override page. Distinguishes workdays, holidays, weekends, and 補班 (make-up workdays).
23. **Monthly punch override** — Employees bulk-edit clock-in/clock-out for any workday of a month via `/dashboard/monthly-override`. HR+ can override any employee (with department filter + employee selector). Overrides mark old logs as `is_overridden=True`, create new logs, and recalculate daily summaries. No approval workflow. Supports pre-filling future days for salary settlement.
24. **LAN dev access** — Frontend `next.config.ts` uses `allowedDevOrigins: ["192.168.2.*"]` (DNS-segment wildcard, NOT CIDR — Next.js splits on `.`). Backend `config.py` has `cors_origin_regex: r"http://192\.168\.\d+\.\d+:3000"` (regex matching any LAN IP). Remove both in production.
25. **Production deployment** — `docker-compose.prod.yml` + `frontend/Dockerfile.prod` (multi-stage, non-root, `npm start`) + `backend/.env.production.example` + `frontend/.env.production.example` templates. Full walkthrough in `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`. Key constraints: `NEXT_PUBLIC_API_URL` is baked in at build time (requires rebuild to change); WebAuthn requires HTTPS + bare-host `RP_ID` equal to the production domain; `seed.py` must NOT be run in prod (ships weak test passwords).
26. **Soft-delete for terminated employees** — `employees.terminated_at` (nullable timestamp) marks resigned employees. Required by Taiwan Labor Standards Act §30(5), which mandates attendance-record retention (5 years minimum). Hard `DELETE /api/employees/{id}` is rejected with 409 when attendance_logs reference the employee; HR must use `POST /api/employees/{id}/terminate` instead (reversible via `/reactivate`). Terminated employees are blocked from password and WebAuthn login (same generic "Invalid credentials" error to avoid enumeration). `GET /api/employees` excludes terminated by default; pass `?include_terminated=true` for HR audit views. Never self-terminate (blocked at API and UI). Reports (`/api/reports/daily`, `/api/reports/export`) also accept `include_terminated`: when an explicit `emp_id` is specified it is always honored regardless of termination (LSA retention takes priority); without `emp_id`, terminated employees are hidden unless `include_terminated=true`. `generate_all_summaries` iterates all employees (so historical summaries for resigned employees are always returned), but skips ABSENT generation for employees already terminated on/before the target date. Only the Reports page surfaces the "Include resigned employees" toggle (HR+) — Monthly Override intentionally does not.

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

**Current test count: 275 backend + 68 frontend = 343 passing + 33 Playwright E2E stubs**
