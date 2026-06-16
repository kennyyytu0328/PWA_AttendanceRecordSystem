# TODO — GoGoFresh Attendance System (TDD Implementation)

**Status:** Phases 0-14 complete. 275 backend tests + 68 frontend tests passing. **Phase 15 (Org Reporting Hierarchy) — planned, in progress on branch `feat/org-reporting-hierarchy`.**

## Phase 0: Project Scaffolding & Test Infrastructure -- DONE

- [x] Create `backend/` with `pyproject.toml` (webauthn, passlib[bcrypt], python-jose, etc.)
- [x] Create `backend/app/config.py` (pydantic-settings BaseSettings from .env)
- [x] Create `backend/app/database.py` (async engine, session maker, get_db dependency)
- [x] Create `backend/tests/conftest.py` (in-memory SQLite fixture, TestClient fixture)
- [x] Create `frontend/` via create-next-app (Next.js 16, TypeScript, Tailwind, App Router)
- [x] Configure `vitest.config.ts` (jsdom) + `playwright.config.ts`
- [x] Create `docker-compose.yml` (PostgreSQL 16, backend, frontend)
- [x] Verify pytest (1 passed) and vitest (1 passed) both green

## Phase 1: Database Models & Core Utilities -- DONE (31 tests)

### 1A: Haversine Distance Calculator -- DONE (8 tests)
- [x] `backend/app/utils/haversine.py` — Pure function with `EARTH_RADIUS_KM`, `_validate_range()`, `Final` constants
- [x] `backend/tests/unit/test_haversine.py` — 8 tests (zero dist, known dist, antipodal, negative coords, boundary in/out, invalid lat/lon)

### 1B: Password Hashing Utility -- DONE (5 tests)
- [x] `backend/app/utils/password.py` — `hash_password()`, `verify_password()` using passlib bcrypt
- [x] `backend/tests/unit/test_password.py` — 5 tests

### 1C: SQLAlchemy/SQLModel Database Models -- DONE (10 tests)
- [x] 5 model files: employee.py (Role enum), authenticator.py, attendance_log.py (WorkMode enum), system_config.py, daily_attendance_summary.py (AttendanceStatus enum)
- [x] Indexes on attendance_logs.timestamp + emp_id, unique constraint on (emp_id, date)
- [x] `backend/tests/unit/test_models.py` — 10 tests

### 1D: Pydantic Schemas -- DONE (7 tests + 1 smoke)
- [x] 4 schema files: employee.py, attendance.py, auth.py, system_config.py
- [x] Field validators: min_length, ge/le on lat/lon/accuracy, ConfigDict(from_attributes=True)
- [x] `backend/tests/unit/test_schemas.py` — 7 tests

## Phase 2: Repository Layer (Data Access) -- DONE (33 tests)

### 2A: Employee Repository -- DONE (11 tests)
- [x] `backend/app/repositories/employee_repository.py` — 8 async functions (CRUD + pagination + department/role filter)
- [x] `backend/tests/unit/test_employee_repository.py` — 11 tests (incl. pagination test)

### 2B: Authenticator Repository -- DONE (5 tests)
- [x] `backend/app/repositories/authenticator_repository.py` — CRUD + sign_count update
- [x] `backend/tests/unit/test_authenticator_repository.py` — 5 tests

### 2C: Attendance Log Repository -- DONE (7 tests)
- [x] `backend/app/repositories/attendance_repository.py` — Append-only, NO update/delete (immutability)
- [x] `backend/tests/unit/test_attendance_repository.py` — 7 tests (incl. immutability assertion)

### 2D: System Config Repository -- DONE (5 tests)
- [x] `backend/app/repositories/system_config_repository.py` — get_by_key, get_office_location, set_config (upsert)
- [x] Uses `datetime.datetime.now(datetime.UTC)` (not deprecated utcnow)
- [x] `backend/tests/unit/test_system_config_repository.py` — 5 tests

### 2E: Summary Repository -- DONE (5 tests)
- [x] `backend/app/repositories/summary_repository.py` — CRUD + upsert + filter by employee/date/status
- [x] `backend/tests/unit/test_summary_repository.py` — 5 tests

## Phase 3: Service Layer (Business Logic) -- DONE (64 tests)

### 3A: Permission Service -- DONE (13 tests)
- [x] `backend/app/services/permission_service.py` — Declarative frozenset permission matrix, 10 action constants, role hierarchy
- [x] `backend/tests/unit/test_permission_service.py` — 13 tests

### 3B: Employee Service -- DONE (10 tests)
- [x] `backend/app/services/employee_service.py` — CRUD + JWT auth (python-jose), no user enumeration, role-based list filtering
- [x] `backend/tests/unit/test_employee_service.py` — 10 tests

### 3C: WebAuthn Service -- DONE (10 tests)
- [x] `backend/app/services/webauthn_service.py` — Register/authenticate, challenge storage in `_challenges` dict, clone detection via sign_count
- [x] `backend/tests/unit/test_webauthn_service.py` — 10 tests (all mock webauthn library)

### 3D: Geolocation Service -- DONE (8 tests)
- [x] `backend/app/services/geolocation_service.py` — `WorkModeResult` frozen dataclass, reads office from system_config, 100m threshold, low accuracy flag
- [x] `backend/tests/unit/test_geolocation_service.py` — 8 tests (incl. boundary 99m/100m)

### 3E: Attendance Service -- DONE (10 tests)
- [x] `backend/app/services/attendance_service.py` — `PunchResult` frozen dataclass, punch orchestration, manager override, mocks geolocation service
- [x] `backend/tests/unit/test_attendance_service.py` — 10 tests

### 3F: Reporting Service -- DONE (13 tests)
- [x] `backend/app/services/reporting_service.py` — `calculate_status()` pure function, 5min grace, LATE precedence, CSV/JSON export
- [x] `backend/tests/unit/test_reporting_service.py` — 13 tests (uses freezegun)

## Phase 4: API Layer (Routers) -- DONE (60 tests)

### 4F: Auth Middleware -- DONE (12 tests)
- [x] `backend/app/middleware/auth_middleware.py` — `get_current_user` (JWT decode), `require_role(minimum_role)` (hierarchy-based)
- [x] `backend/tests/unit/test_auth_middleware.py` — 12 tests (valid token, missing header, invalid scheme, expired, bad signature, malformed, role access/deny)

### 4A: Authentication Router -- DONE (9 tests)
- [x] `backend/app/routers/auth.py` — login, /me, WebAuthn register/authenticate options+verify
- [x] `backend/tests/integration/test_auth_api.py` — 9 tests (login success/fail/missing, token flow, WebAuthn mocked)

### 4B: Employee Router -- DONE (11 tests)
- [x] `backend/app/routers/employees.py` — CRUD + role-based permissions
- [x] `backend/tests/integration/test_employee_api.py` — 11 tests (create HR/forbidden, get/404, list, update, self-update, role change denied, delete ADMIN, unauth)

### 4C: Attendance Router -- DONE (10 tests)
- [x] `backend/app/routers/attendance.py` — punch, today, history, team, all, override
- [x] `backend/tests/integration/test_attendance_api.py` — 10 tests (punch success/unauth/invalid, today, history, team/forbidden, all/forbidden, override)
- [x] Added `get_history`, `get_team_logs`, `get_all_logs` to attendance_service.py

### 4D: Reports Router -- DONE (10 tests)
- [x] `backend/app/routers/reports.py` — daily report, CSV/JSON export, generate summaries
- [x] `backend/tests/integration/test_reports_api.py` — 10 tests (daily/forbidden/missing, CSV/JSON export, export forbidden, generate ADMIN/forbidden)
- [x] Added `get_daily_report` to reporting_service.py

### 4E: System Config Router -- DONE (9 tests)
- [x] `backend/app/routers/system_config.py` — office-location get/set, config CRUD
- [x] `backend/tests/integration/test_system_config_api.py` — 9 tests (office location CRUD, config CRUD, role enforcement, unauth)

## Phase 5: Frontend Core Infrastructure -- DONE (27 tests)

### 5A: TypeScript Types & API Client -- DONE (9 tests)
- [x] `frontend/src/types/index.ts` — All shared types (Employee, Role, AttendanceLog, PunchRequest, etc.)
- [x] `frontend/src/lib/api.ts` — Typed API client with JWT auth interceptor, ApiError class
- [x] `frontend/src/lib/validators.ts` — Zod schemas (loginRequest, punchRequest, employeeCreate, officeLocation)
- [x] `frontend/__tests__/unit/lib/api.test.ts` — 9 tests (GET/POST/PUT/DELETE, auth header, ApiError, Zod validation)

### 5B: Geolocation Hook -- DONE (6 tests)
- [x] `frontend/src/hooks/useGeolocation.ts` — useGeolocation hook with high accuracy, error handling
- [x] `frontend/__tests__/unit/hooks/useGeolocation.test.ts` — 6 tests (initial state, loading, success, error, permission denied, not supported)

### 5C: WebAuthn Hook -- DONE (6 tests)
- [x] `frontend/src/hooks/useWebAuthn.ts` — useWebAuthn hook with register/authenticate flows
- [x] `frontend/__tests__/unit/hooks/useWebAuthn.test.ts` — 6 tests (supported/unsupported, register flow, auth flow, error handling)

### 5D: Auth Context & Login Page -- DONE (6 tests)
- [x] `frontend/src/lib/auth-context.tsx` — AuthProvider with JWT decode, login/logout, localStorage persistence
- [x] `frontend/src/app/login/page.tsx` — Login form with Zod validation, error display, redirect on success
- [x] `frontend/__tests__/unit/app/login.test.tsx` — 6 tests (null user, restore token, login, logout, form render, error display)

## Phase 6: Frontend Feature Pages -- DONE (33 tests)

### 6A: Punch Page -- DONE (8 tests)
- [x] `frontend/src/app/punch/page.tsx` — Large punch button, GPS request, result display, low accuracy warning, Framer Motion animations
- [x] `frontend/__tests__/unit/app/punch.test.tsx` — 8 tests (render, loading, result, geolocation error, API error, auth redirect, accuracy warning, disabled)

### 6B: Dashboard Page -- DONE (6 tests)
- [x] `frontend/src/app/dashboard/page.tsx` — Welcome message, today's stats, role-based nav links, loading skeleton
- [x] `frontend/__tests__/unit/app/dashboard.test.tsx` — 6 tests (welcome, attendance data, loading, nav links, manager links, employee restrictions)

### 6C: Attendance History Page -- DONE (7 tests)
- [x] `frontend/src/app/attendance/page.tsx` — Table with date filters, work mode badges, override indicators, empty state
- [x] `frontend/__tests__/unit/app/attendance.test.tsx` — 7 tests (heading, loading, records, badges, empty state, override, date filters)

### 6D: Admin Panel -- DONE (7 tests)
- [x] `frontend/src/app/admin/page.tsx` — Employee management, office location, system config sections with role-based visibility
- [x] `frontend/__tests__/unit/app/admin.test.tsx` — 7 tests (heading, HR sections, ADMIN config, access denied, employee list, location form)

### 6E: PWA Configuration -- DONE (5 tests)
- [x] `frontend/public/manifest.json` — Web App Manifest with icons, standalone display
- [x] `frontend/src/lib/pwa.ts` — isPWAInstalled, canInstallPWA, registerServiceWorker utilities
- [x] Updated `frontend/src/app/layout.tsx` — manifest link, theme color, updated title/description
- [x] `frontend/__tests__/unit/pwa.test.ts` — 5 tests (manifest fields, standalone detection, service worker, install prompt)

## Phase 7: End-to-End Tests -- DONE (5 backend + 33 frontend stubs)

### 7A: Backend E2E -- DONE (5 tests)
- [x] `backend/tests/e2e/test_punch_workflow.py` — 5 full workflow tests:
  - Full onboarding flow (ADMIN → HR → EMPLOYEE creation chain)
  - Full punch flow (set office location → punch with GPS → verify logs)
  - Full reporting flow (seed data → generate summaries → export CSV/JSON)
  - Role-based access flow (EMPLOYEE/MANAGER/HR/ADMIN permission boundaries)
  - Office location change flow (set → verify → update → verify)

### 7B: Frontend E2E (Playwright) -- DONE (33 test stubs)
- [x] `frontend/__tests__/e2e/login-and-punch.spec.ts` — 6 test stubs
- [x] `frontend/__tests__/e2e/attendance-history.spec.ts` — 6 test stubs
- [x] `frontend/__tests__/e2e/admin-employees.spec.ts` — 7 test stubs
- [x] `frontend/__tests__/e2e/office-location.spec.ts` — 7 test stubs
- [x] `frontend/__tests__/e2e/pwa.spec.ts` — 7 test stubs
- All use `test.fixme()` markers — ready to run when full stack is deployed

## Phase 8: Security Hardening & Final Polish -- DONE (31 tests)

- [x] SQL injection prevention tests (3 tests)
- [x] XSS prevention / input sanitization tests (4 tests)
- [x] Rate limiting on login — 5 attempts/min, 429 after (3 tests)
- [x] CORS configuration — configurable origins via settings (4 tests)
- [x] Secure headers — X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, HSTS, CSP (6 tests)
- [x] No user enumeration — same error for wrong password / non-existent user (3 tests)
- [x] JWT expiry validation (3 tests)
- [x] Password hashing — bcrypt, never plaintext (5 tests)
- [x] Code audit: no print statements, no hardcoded secrets, all endpoints auth-guarded
- [x] `backend/app/middleware/rate_limiter.py` — in-memory rate limiter
- [x] `backend/app/config.py` — added cors_origins setting
- [x] `backend/app/main.py` — CORS middleware + secure headers middleware
- [x] `backend/tests/unit/test_security.py` — 31 security tests

## Phase 9: Bug Fixes & Enhancements

### 9A: WorkMode Enum Mismatch Fix -- DONE
- [x] **Bug**: Frontend used `"WFO"` for office work mode, but backend enum uses `"OFFICE"` — caused team/attendance/punch pages to always display WFH badge
- [x] `frontend/src/types/index.ts` — Changed `WorkMode` type from `"WFO" | "WFH"` to `"OFFICE" | "WFH"`
- [x] `frontend/src/app/team/page.tsx` — Updated `WorkModeBadge` to check `"OFFICE"` instead of `"WFO"`
- [x] `frontend/src/app/attendance/page.tsx` — Updated `WorkModeBadge` to check `"OFFICE"` instead of `"WFO"`
- [x] `frontend/src/app/punch/page.tsx` — Updated punch result display to check `"OFFICE"` instead of `"WFO"`

### 9B: Date Range Query Support -- DONE
- [x] `backend/app/services/attendance_service.py` — Refactored `get_team_logs`, `get_all_logs`, `get_history` to accept `start_date`/`end_date` instead of single `date`
- [x] `backend/app/routers/attendance.py` — Updated endpoints to require `start_date`/`end_date` query params
- [x] `backend/app/services/reporting_service.py` — Refactored to generate multi-day attendance summaries
- [x] `backend/app/routers/reports.py` — Updated daily report endpoint to support date range queries
- [x] `frontend/src/app/team/page.tsx` — Added date range picker UI, updated API calls for date range
- [x] `frontend/src/app/reports/page.tsx` — Added date range picker to DailyReportSection
- [x] `frontend/src/messages/en.json` / `zh.json` — Added i18n keys for date range picker
- [x] Updated all backend integration and e2e tests to use date range parameters
- [x] Fixed date display in Team page Time column after date range implementation

### 9C: WebAuthn Fingerprint Authentication (Frontend) -- DONE
- [x] `frontend/src/app/login/page.tsx` — Added fingerprint login button using `useWebAuthn` hook
- [x] `frontend/src/lib/auth-context.tsx` — Added `loginWithToken` method to AuthContext for token-based login
- [x] `frontend/src/hooks/useWebAuthn.ts` — Refactored `authenticate` to return token instead of storing directly; fixed hydration error with client-side effect
- [x] `frontend/src/app/dashboard/page.tsx` — Added fingerprint registration/removal section with credential management UI
- [x] `backend/app/repositories/authenticator_repository.py` — Added `delete_by_employee_id` for bulk credential deletion
- [x] `backend/app/routers/auth.py` — Added WebAuthn credential list/delete management endpoints
- [x] `backend/app/services/webauthn_service.py` — Fixed credential ID encoding mismatch (base64url consistency)
- [x] `frontend/src/messages/en.json` / `zh.json` — Added i18n keys for fingerprint login, registration, and removal
- [x] Verified fingerprint registration and authentication working end-to-end with Windows Hello

### 9D: Back to Dashboard Navigation -- DONE
- [x] `frontend/src/components/BackButton.tsx` — Reusable `ArrowLeft` + "Dashboard" link component
- [x] Added `BackButton` to all 5 sub-pages: punch (absolute top-left), attendance, team, reports, admin (above page header)
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `common.backToDashboard` i18n key

## Phase 10: Meeting Requirements — Tardiness, Reasons, Export Enhancements -- DONE

### 10A: Configurable Grace Period -- DONE
- [x] `backend/app/repositories/system_config_repository.py` — Added `get_grace_period()` helper (reads from `system_config` table, defaults to 5 min)
- [x] `backend/app/services/reporting_service.py` — `calculate_status()` now takes `grace_minutes` param; `generate_daily_summary()` reads grace period from DB
- [x] `backend/app/routers/system_config.py` — Added `GET/PUT /api/config/grace-period` endpoints (HR+ can update, any auth user can read)
- [x] `frontend/src/app/admin/page.tsx` — Added `GracePeriodSection` component (number input 0-60 min, visible to HR+)
- [x] `frontend/src/messages/en.json` / `zh.json` — Added i18n keys for grace period UI

### 10B: Tardiness Alert on Punch Page -- DONE
- [x] `backend/app/services/attendance_service.py` — Added `_check_tardiness()` helper; `PunchResult` now includes `tardiness_status` and `summary_id`
- [x] `backend/app/schemas/attendance.py` — Added `tardiness_status` and `summary_id` to `PunchResponse`
- [x] `backend/app/routers/attendance.py` — Passes tardiness fields through to response
- [x] `frontend/src/types/index.ts` — Added `tardiness_status` and `summary_id` to `PunchResponse` type
- [x] `frontend/src/app/punch/page.tsx` — Shows red alert (LATE) or amber alert (EARLY_LEAVE) after punch
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `punch.lateAlert`, `punch.earlyLeaveAlert` i18n keys

### 10C: Employee Late/Early-Leave Reason Entry -- DONE
- [x] `backend/app/models/attendance_reason.py` — New `AttendanceReason` model (id, summary_id, emp_id, reason, created_at)
- [x] `backend/app/models/__init__.py` — Registered `AttendanceReason` model
- [x] `backend/alembic/versions/a1b2c3d4e5f6_add_attendance_reasons.py` — Migration for `attendance_reasons` table
- [x] `backend/app/schemas/attendance_reason.py` — `ReasonSubmitRequest` and `ReasonResponse` schemas
- [x] `backend/app/repositories/reason_repository.py` — `create_reason`, `find_by_summary_id`, `find_by_employee`
- [x] `backend/app/repositories/summary_repository.py` — Added `find_by_id()` method
- [x] `backend/app/services/reason_service.py` — `submit_reason` (validates ownership, status, uniqueness), `get_reasons_for_employee`, `get_reason_for_summary`
- [x] `backend/app/routers/reasons.py` — `POST /api/reasons`, `GET /api/reasons/me`, `GET /api/reasons?emp_id=...` (MANAGER+)
- [x] `backend/app/main.py` — Registered reasons router
- [x] `backend/app/services/attendance_service.py` — Auto-generates daily summary when tardy punch detected (provides `summary_id` for immediate reason submission)
- [x] `frontend/src/app/punch/page.tsx` — Reason textarea + submit button appears when LATE/EARLY_LEAVE; success confirmation after submission
- [x] `frontend/src/messages/en.json` / `zh.json` — Added reason form i18n keys

### 10D: Individual Employee Export -- DONE
- [x] `backend/app/services/reporting_service.py` — `export_attendance()` and `get_daily_report()` accept optional `emp_id` filter
- [x] `backend/app/routers/reports.py` — Added `emp_id` query param to `/api/reports/daily` and `/api/reports/export`
- [x] `frontend/src/app/reports/page.tsx` — Added employee selector dropdown to both `DailyReportSection` and `ExportSection`
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `reports.employee`, `reports.employeePlaceholder` i18n keys

### 10E: Excel (.xlsx) Export -- DONE
- [x] `backend/pyproject.toml` — Added `openpyxl>=3.1.0` dependency
- [x] `backend/app/services/reporting_service.py` — `export_attendance()` supports `format="xlsx"` with bold headers, auto-filter, auto-sized columns
- [x] `backend/app/routers/reports.py` — Returns xlsx as binary response with proper Content-Type and Content-Disposition
- [x] `frontend/src/app/reports/page.tsx` — Added "Excel" option to format dropdown; blob download for xlsx

### 10F: Geolocation Test Fix -- DONE
- [x] `backend/tests/unit/test_geolocation_service.py` — Updated tests from 100m threshold to 2km threshold (added `_OFFSET_2KM`, `_OFFSET_3KM` offsets; fixed assertions)

## Phase 11: Bug Fixes & Admin Enhancements -- DONE

### 11A: Department Management -- DONE
- [x] `backend/app/repositories/system_config_repository.py` — Added `get_departments()` helper
- [x] `backend/app/routers/system_config.py` — Added `GET/PUT /api/config/departments` endpoints (HR+ can update, any auth user can read)
- [x] `frontend/src/app/admin/page.tsx` — Added `DepartmentManagementSection` (tag-based UI with add/remove)
- [x] `frontend/src/app/admin/page.tsx` — Changed department field from free-text `<input>` to `<select>` dropdown in both create and edit employee forms
- [x] `frontend/src/messages/en.json` / `zh.json` — Added i18n keys for department management

### 11B: Office Location Display Fix -- DONE
- [x] `frontend/src/app/admin/page.tsx` — Shows current lat/lon values when configured, or "not been set before" amber banner when not configured
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `admin.locationNotSet`, `admin.currentLocation` i18n keys

### 11C: Single-Punch Late Status Fix -- DONE
- [x] `backend/app/services/reporting_service.py` — `calculate_status()` now returns LATE (not ABNORMAL) when a single punch is past the grace deadline. ABNORMAL only for single on-time punches.
- [x] Design decision: single punch = clock-in; if late, status is LATE. Forgotten clock-in is handled via manager override.

### 11D: Attendance Reason Submission Fixes -- DONE
- [x] `backend/app/models/attendance_reason.py` — Fixed `created_at` from timezone-aware `datetime.now(UTC)` to naive `datetime.now` to match PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` column
- [x] `backend/alembic/versions/a1b2c3d4e5f6_add_attendance_reasons.py` — Must run `alembic upgrade head` to create `attendance_reasons` table

### 11E: Shift Time Validation -- DONE
- [x] `backend/app/schemas/employee.py` — Added `model_validator` to `EmployeeCreate` and `EmployeeUpdate` to reject `shift_end_time <= shift_start_time`

### 11F: Attendance History Status Column -- DONE
- [x] `backend/app/routers/attendance.py` — Added `GET /api/attendance/summaries` endpoint (employee's own daily summaries)
- [x] `frontend/src/app/attendance/page.tsx` — Fetches daily summaries and displays status badges (Normal/Late/Early Leave/Abnormal) per date; date and status only shown on first row of each date group
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `attendance.statusNormal`, `statusLate`, `statusEarlyLeave`, `statusAbnormal` i18n keys

### 11G: LATE_AND_EARLY_LEAVE Combined Status -- DONE
- [x] `backend/app/models/daily_attendance_summary.py` — Added `LATE_AND_EARLY_LEAVE` to `AttendanceStatus` enum
- [x] `backend/alembic/versions/b2c3d4e5f6a7_add_late_and_early_leave_status.py` — Migration to add new enum value to PostgreSQL
- [x] `backend/app/services/reporting_service.py` — `calculate_status()` returns `LATE_AND_EARLY_LEAVE` when employee is both late and leaves early
- [x] `backend/app/services/reason_service.py` — Allows reason submission for `LATE_AND_EARLY_LEAVE` status
- [x] `backend/tests/unit/test_models.py` — Updated enum length assertion from 4 to 5
- [x] `frontend/src/types/index.ts` — Added `LATE_AND_EARLY_LEAVE` to `AttendanceStatus` type
- [x] `frontend/src/app/punch/page.tsx` — Shows both LATE and EARLY_LEAVE alerts for combined status; reason check covers new status
- [x] `frontend/src/app/attendance/page.tsx` — StatusBadge handles `LATE_AND_EARLY_LEAVE`
- [x] `frontend/src/app/reports/page.tsx` — StatusBadge, label map, and filter dropdown handle `LATE_AND_EARLY_LEAVE`
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `statusLateAndEarlyLeave` keys ("Late & Early Leave" / "遲到且早退")

### 11H: Team Page Status Column -- DONE
- [x] `frontend/src/app/team/page.tsx` — Fetches daily summaries via `/api/reports/daily` and displays StatusBadge per employee+date group
- [x] `frontend/src/app/team/page.tsx` — Groups rows by employee+date: emp_id and status only shown on first row, thicker border between groups

### 11I: Punch Page Duplicate Reason Prevention -- DONE
- [x] `frontend/src/app/punch/page.tsx` — After tardy punch, checks `/api/reasons/me` to see if reason already submitted for that summary; shows "already submitted" instead of form

## Phase 12: Absent Status Tracking -- DONE (6 tests)

### 12A: Absent Status Tracking -- DONE
- [x] `backend/app/models/daily_attendance_summary.py` — Added `ABSENT` to `AttendanceStatus` enum (6 values total)
- [x] `backend/alembic/versions/c3d4e5f6a7b8_add_absent_status.py` — Migration adds `ABSENT` enum value to PostgreSQL
- [x] `backend/app/services/reporting_service.py` — `generate_all_summaries()` now also generates `ABSENT` summaries for non-punching employees on workdays (Taiwan calendar via `is_workday_from_data`, fallback Mon-Fri for weekends)
- [x] `backend/app/services/reporting_service.py` — Added `_load_calendar_for_year()` helper to read cached Taiwan calendar data from `system_config`; no ABSENT generation on holidays / weekends
- [x] Monthly override / manager punch insertion automatically replaces an ABSENT summary via existing `upsert_summary` flow (no special code needed)
- [x] `backend/tests/unit/test_reporting_service.py` — Added 5 new tests: absent for non-punching, skip on holiday, skip on weekend, null clock times, override replaces absent
- [x] `backend/tests/integration/test_reports_api.py` — Added `test_generate_summaries_includes_absent_count`
- [x] `backend/tests/unit/test_models.py` — Enum length updated 5 → 6
- [x] `backend/tests/e2e/test_punch_workflow.py` — Relaxed export sort-order assertion (other users may now get ABSENT summaries)
- [x] `frontend/src/types/index.ts` — Added `"ABSENT"` to `AttendanceStatus` type union
- [x] `frontend/src/app/attendance/page.tsx`, `team/page.tsx`, `reports/page.tsx` — `StatusBadge` handles `ABSENT` (red background) with proper i18n label; reports page now has both `ABNORMAL` and `ABSENT` filter options, and `ABNORMAL` is labeled correctly (was incorrectly displayed as "ABSENT" before Phase 12)
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `attendance.statusAbsent` ("Absent" / "缺勤") and `reports.statusAbnormal` ("ABNORMAL" / "異常")

## Phase 13: Monthly Punch Override & Team Reason Column -- DONE (44 tests)

### 13A: Team Page Reason Column -- DONE
- [x] `backend/app/repositories/reason_repository.py` — Added `find_by_summary_ids()` for bulk reason lookup
- [x] `backend/app/routers/reports.py` — `/api/reports/daily` now includes `reason` field (joined from `attendance_reasons` table)
- [x] `frontend/src/app/team/page.tsx` — Added "Reason" column displaying employee-submitted reasons next to status
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `team.reason` i18n key ("Reason" / "事由")

### 13B: Monthly Punch Override (Dashboard Quick Action) -- DONE
Employee can bulk-edit first clock-in and last clock-out times for any day of the month. Takes effect immediately (no approval). Supports pre-filling future days for salary settlement. Integrated with Taiwan workday calendar.

#### Taiwan Workday Calendar
- [x] `backend/app/utils/taiwan_calendar.py` — `DayInfo` dataclass, `parse_calendar_json()`, `is_workday_from_data()`, `get_month_info_from_data()`, `fetch_calendar_from_cdn()` — auto-fetches from ruyut/TaiwanCalendar CDN
- [x] `backend/app/repositories/system_config_repository.py` — Added `get_workday_calendar()`, `set_workday_calendar()` helpers (cached in `system_config` table)
- [x] `backend/app/routers/system_config.py` — Added `GET /api/config/workdays`, `POST /api/config/workdays/refresh` (HR+), `GET /api/config/workdays/status` (HR+)

#### Backend
- [x] `backend/app/schemas/bulk_override.py` — `BulkOverrideEntry`, `BulkOverrideRequest`, `BulkOverrideDayResult`, `BulkOverrideResponse`
- [x] `backend/app/repositories/attendance_repository.py` — Added `mark_overridden_by_employee_and_date()` (marks old logs, preserves content)
- [x] `backend/app/services/attendance_service.py` — Added `bulk_override_punches()` with permission checks (EMPLOYEE=self only, HR+=any), override marking, new log creation, summary recalculation
- [x] `backend/app/routers/attendance.py` — Added `PUT /api/attendance/override-bulk` endpoint
- [x] Original raw punch records preserved in `attendance_logs` for HR/Manager audit trail
- [x] Supports pre-filling future dates (creates new attendance log entries)

#### Frontend
- [x] `frontend/src/types/index.ts` — Added `WorkdayInfo`, `WorkdaysResponse`, `CalendarStatus`, `CalendarStatusResponse`, `BulkOverrideEntry`, `BulkOverrideRequest`, `BulkOverrideDayResult`, `BulkOverrideResponse`
- [x] `frontend/src/app/dashboard/page.tsx` — Added "Monthly Punch Override" quick action card
- [x] `frontend/src/app/dashboard/monthly-override/page.tsx` — Full monthly calendar table with editable time inputs, holiday/weekend rows greyed out, 補班 rows with amber badge, HR employee selector, Save All with feedback
- [x] `frontend/src/app/admin/page.tsx` — Added `CalendarStatusSection` (HR+) showing loaded calendar years, last updated, "更新全年行事曆" refresh button
- [x] `frontend/src/messages/en.json` / `zh.json` — Added i18n keys for monthly override and calendar status

#### Tests
- [x] `backend/tests/unit/test_taiwan_calendar.py` — 18 tests (parsing, workday detection, month info, CDN fetch)
- [x] `backend/tests/unit/test_bulk_override_service.py` — 7 tests (create logs, mark overridden, recalculate summaries, permissions, validation)
- [x] `backend/tests/integration/test_workday_api.py` — 7 tests (GET workdays, auto-fetch, refresh HR/forbidden, status HR/forbidden)
- [x] `backend/tests/integration/test_bulk_override_api.py` — 5 tests (success, HR for other, unauth, empty entries, permission error)
- [x] `frontend/__tests__/unit/app/monthly-override.test.tsx` — 7 tests (page render, calendar table, holidays, save flow, HR selector)

## Phase 14: UX Enhancements -- DONE

### 14D: Leave Remarks + Monthly Submission + Chinese Export + ADMIN-only Delete -- DONE (2026-05-14)
Nine-item meeting-minutes bundle from 2026-05-13. Reverses the prior HR-can-hard-delete decision (see CLAUDE.md #30).
- [x] **Backend**: `AttendanceStatus.LEAVE` enum + `daily_attendance_summaries.leave_type` (max 50) + `remark` (max 500) columns (Alembic migration `f6a7b8c9d0e1`)
- [x] **Backend**: `monthly_submissions` table with `UNIQUE(emp_id, year, month)`; repository + service + `POST/GET /api/monthly-submissions` (self-or-HR+)
- [x] **Backend**: `system_config.leave_types` config; `GET /api/admin/leave-types` (any auth) + `PUT` (HR+)
- [x] **Backend**: `calculate_status` short-circuits to LEAVE when `leave_type` is set; `generate_daily_summary` preserves leave fields; `generate_all_summaries` skips ABSENT for leave days
- [x] **Backend**: bulk_override accepts leave_type/remark per entry (no-op rows with only leave fields persist)
- [x] **Backend**: `/api/reports/daily` + `/api/reports/export` accept `submission_filter`; non-HR/non-ADMIN server-forced to `submitted`
- [x] **Backend**: Export Chinese-ized headers + `shift_time` + `remark` + `reason` + `submission_status` columns; JSON keeps English
- [x] **Backend**: `DELETE /api/employees/{id}` requires `Role.ADMIN` (reversed from HR); 409 LSA-retention guard retained
- [x] **Frontend**: `RemarkCell` component (leave-type dropdown + remark input, React.memo, controlled)
- [x] **Frontend**: `WarningModal` (month-level — lists all abnormal days; "返回修改" / "繼續送出"; Escape + backdrop dismiss)
- [x] **Frontend**: Monthly-override page wires RemarkCell + WarningModal + "本月送單" button + submission-status badge
- [x] **Frontend**: Reports page adds 班別時間 / 備註 / 遲到理由 / 送單狀態 columns + HR-only submission filter (submitted/unsubmitted/all)
- [x] **Frontend**: Admin leave-types tab (list/add/remove/save); Delete button hidden for HR (ADMIN-only)
- [x] **Frontend**: Typed API client modules `frontend/src/lib/api/monthly-submissions.ts` + `leave-types.ts`
- [x] **i18n**: Added zh + en keys for status.leave, monthlyOverride.{remark,leaveType,leaveTypeNone,submitMonth,warningTitle,warningBody,backToEdit,proceed,submitting,submitSuccess,submitted,notSubmitted,submittedAt}, reports.{shiftTime,remark,reason,submissionStatus,submitted,unsubmitted,submissionFilter,filterAll,filterSubmitted,filterUnsubmitted}, admin.{leaveTypes,leaveTypesAdd,leaveTypesRemove,leaveTypes{Empty,Placeholder,Duplicate,Saved,SaveError,LoadError}}
- [x] **Tests**: Backend test suite extended (333+ passing); Frontend +29 tests (124 passing total); Playwright stubs at `frontend/__tests__/e2e/monthly-submission-flow.spec.ts`

### 14A: Monthly Override Department Filter -- DONE
- [x] `frontend/src/app/dashboard/monthly-override/page.tsx` — Added department filter dropdown (HR+ only) before employee selector; selecting a department filters the employee list; changing department resets employee selection
- [x] `frontend/src/messages/en.json` / `zh.json` — Added `monthlyOverride.filterDepartment` and `monthlyOverride.allDepartments` i18n keys

### 14C: LAN Access for Dev Testing -- DONE
Enable testing the dev server from other devices on the local subnet (phones, tablets) at `http://192.168.2.<host>:3000`.
- [x] `frontend/next.config.ts` — Added `allowedDevOrigins: ["192.168.2.*"]` (unblocks Next.js HMR cross-origin guard). Note: DNS-segment wildcard, NOT CIDR — `192.168.2.0/24` does NOT work because Next.js splits on `.` and compares segments
- [x] `backend/app/config.py` — Added `cors_origin_regex: str | None = r"http://192\.168\.\d+\.\d+:3000"` setting
- [x] `backend/app/main.py` — Passed `allow_origin_regex=settings.cors_origin_regex` to `CORSMiddleware` (complements literal `allow_origins` list)
- [x] Backend must be started with `uvicorn --host 0.0.0.0` to bind all interfaces (not just loopback)
- [x] Known limitation: Fingerprint/WebAuthn will NOT work over LAN HTTP — browsers mandate HTTPS for any origin other than `localhost`. Password login works fine.

### 14D: Production Deployment Templates & Guide -- DONE
Created reusable templates for deploying this PWA to a prod environment with HTTPS, domain-bound WebAuthn, and Docker Compose.
- [x] `backend/.env.production.example` — Template with placeholders for `DATABASE_URL`, `SECRET_KEY` (via `openssl rand -hex 32`), `CORS_ORIGINS`, `WEBAUTHN_RP_ID` (bare host), `WEBAUTHN_ORIGIN` (https)
- [x] `frontend/.env.production.example` — `NEXT_PUBLIC_API_URL` template. Flagged that `NEXT_PUBLIC_*` is baked into the JS bundle at `next build` time — rebuild required on change
- [x] `frontend/Dockerfile.prod` — Multi-stage build: `deps` → `builder` (runs `npm run build` with `NEXT_PUBLIC_API_URL` as build-arg) → `runner` (slim node:22-alpine, non-root user, `npm start`). Replaces the dev Dockerfile which runs `npm run dev`
- [x] `docker-compose.prod.yml` — No bind mounts, no `--reload`, `--workers 4` for uvicorn, postgres NOT published to host (internal-only via `expose:`), `restart: unless-stopped`, builds frontend with `NEXT_PUBLIC_API_URL` build-arg
- [x] `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` — 11-section walkthrough: prerequisites, DNS/domain, secret generation, filling all 3 env files (backend/.env, frontend/.env.production, root compose `.env`), `alembic upgrade head`, inline Python snippet to create the initial ADMIN user (explicitly NOT running `seed.py` in prod because it ships weak passwords), Caddy vs nginx reverse proxy options with TLS termination, smoke-test curl commands, nightly pg_dump backup cron, upgrade flow, pre-flight checklist, troubleshooting table (7 common issues)
- [x] `.gitignore` — Whitelisted `!.env.*.example` pattern so production templates are tracked (they match the `.env.*` ignore rule otherwise)

### 14B: Frontend Test Migration Repair (41 pre-existing failures) -- DONE
Post-i18n/Phase-9C/Phase-11G test drift — tests written in Phases 5/6 had not been updated after later refactors. Now 68/68 frontend unit tests green.
- [x] `frontend/vitest.setup.ts` — Global `vi.mock("@/lib/i18n")` resolving real `en.json` translations (fixes ~35 "useTranslation must be used within an I18nProvider" errors across hooks and page tests)
- [x] `frontend/vitest.setup.ts` — Global mock for `@/components/LanguageSwitcher` → null renderer
- [x] `frontend/__tests__/unit/hooks/useWebAuthn.test.ts` — Updated 2 tests to match Phase 9C `authenticate()` API: returns `string | null` (token) instead of `boolean`; no longer stores token internally (caller uses `AuthContext.loginWithToken`); updated verify payload to spread `{...credential, emp_id}` (not `{credential, emp_id}`)
- [x] `frontend/__tests__/unit/app/login.test.tsx` — JWT payload fake uses `sub` field (matches `decodeToken` which reads `payload.sub`) instead of `emp_id`
- [x] `frontend/__tests__/unit/app/attendance.test.tsx` — Work mode mock values updated `"WFO"` → `"OFFICE"` (Phase 9A enum alignment); added mock for second parallel `GET /api/attendance/summaries` call (Phase 11F) via `mockImplementation`
- [x] `frontend/__tests__/unit/app/admin.test.tsx` — `mockAdminApi()` helper returning properly-shaped payloads for all config endpoints (`/api/config/departments` → `{departments}`, `/api/config/office-location` → `{key, value}`, `/api/config/workdays/status` → `{calendars}`, `/api/config/grace-period` → `{minutes}`) — was crashing on `undefined.length`/`undefined.map` in DepartmentManagement and CalendarStatus sections
- [x] `frontend/__tests__/unit/app/dashboard.test.tsx` — Switched from `getByRole("link", {name: /punch/i})` to `container.querySelector('a[href="/punch"]')` to avoid ambiguity with "Monthly Punch Override" NavLinkCard added in Phase 13B

### 14E: Employee Soft-Delete for Labor-Law Retention -- DONE (6 tests)
Taiwan Labor Standards Act §30(5) requires attendance records to be retained (5 years minimum). Hard-deleting an employee with punch history would destroy legally-required data and fail on the `attendance_logs.emp_id` FK. Added a soft-delete pathway so HR can mark resigned employees inactive while preserving history.

#### Backend
- [x] `backend/app/models/employee.py` — Added `terminated_at: datetime | None` (nullable, timezone-aware, indexed)
- [x] `backend/alembic/versions/d4e5f6a7b8c9_add_terminated_at_to_employees.py` — Migration: add column + index
- [x] `backend/app/schemas/employee.py` — `EmployeeResponse.terminated_at` exposed to clients
- [x] `backend/app/repositories/employee_repository.py` — Added `terminate_employee()`, `reactivate_employee()`, `has_attendance_logs()` (safety check for hard delete); `find_all()` / `find_by_department()` / `find_by_role()` / `find_by_manager_department()` now exclude terminated by default (opt-in via `include_terminated=True`)
- [x] `backend/app/services/employee_service.py` — `terminate_employee()` / `reactivate_employee()` services; `authenticate()` rejects terminated with generic `Invalid credentials` (no account-state leak); `list_employees()` honors `include_terminated` for HR/ADMIN only
- [x] `backend/app/routers/employees.py` — `POST /api/employees/{id}/terminate` + `/reactivate` (HR+); `GET /api/employees?include_terminated=true`; `DELETE /api/employees/{id}` returns 409 if attendance_logs exist (prevents accidental history loss); self-termination + self-delete both blocked with 400
- [x] `backend/app/routers/auth.py` — WebAuthn login path also rejects terminated employees (401)

#### Frontend
- [x] `frontend/src/types/index.ts` — Added optional `Employee.terminated_at?: string | null`
- [x] `frontend/src/app/admin/page.tsx` — "Show resigned employees" toggle (drives `?include_terminated=`); terminated rows show grey styling + "Resigned" badge with tooltip showing termination date; action column swaps Trash/UserMinus for active rows and UserCheck for terminated rows; handlers for terminate/reactivate with localized confirm dialogs
- [x] `frontend/src/messages/en.json` / `zh.json` — Added i18n keys: `terminateEmployee`, `confirmTerminateEmployee`, `employeeTerminated`, `reactivateEmployee`, `confirmReactivateEmployee`, `employeeReactivated`, `terminatedBadge`, `terminatedOn`, `showTerminated`, `hideTerminated`, and matching error messages

#### Tests
- [x] `backend/tests/integration/test_employee_api.py::TestTerminateEmployee` — 5 tests: HR can terminate, self-termination rejected (400), terminated employee's password login is blocked (401), reactivate restores login, list filter respects `include_terminated`
- [x] `backend/tests/integration/test_employee_api.py::TestDeleteEmployee::test_delete_employee_with_logs_blocked` — 1 test: hard DELETE returns 409 when attendance_logs reference the employee

#### Documentation
- [x] `CLAUDE.md` — Added design decision #26 documenting the soft-delete pathway and labor-law rationale

### 14F: Reports Audit Toggle + Terminated-Summary Regression Fix -- DONE (1 test)
Restored visibility of resigned employees' historical records on the Reports page and fixed a regression introduced by 14E. After 14E, `generate_all_summaries()` called `employee_repository.find_all()` which default-excluded terminated employees, so their existing summaries in `daily_attendance_summaries` (e.g., a LATE row for the day of termination) were silently dropped from `/api/reports/daily` — even when HR explicitly filtered by `emp_id=<terminated-id>`. This violated LSA retention intent.

#### Backend
- [x] `backend/app/services/reporting_service.py::generate_all_summaries` — Now fetches employees with `include_terminated=True` so historical summaries for resigned employees are always returned. ABSENT generation guarded: skipped when `emp.terminated_at is not None and emp.terminated_at.date() <= date` (a resigned employee can't be marked absent for days on/after their termination date).
- [x] `backend/app/services/reporting_service.py::get_daily_report` — Added `include_terminated: bool = False` parameter. When an explicit `emp_id` is passed, it is always honored regardless of termination (LSA retention priority). Without `emp_id`, summaries belonging to terminated employees are filtered out unless `include_terminated=True`.
- [x] `backend/app/services/reporting_service.py::export_attendance` — Same `include_terminated` parameter; propagated to `find_by_department` / `find_all`. Explicit `emp_id` export always succeeds for terminated employees.
- [x] `backend/app/routers/reports.py` — Both `GET /api/reports/daily` and `GET /api/reports/export` accept `include_terminated` query param (HR/audit use).

#### Frontend
- [x] `frontend/src/app/reports/page.tsx` — Existing "Include resigned employees" checkbox now also appends `?include_terminated=true` to the daily-report fetch and CSV/JSON/XLSX export URLs. Employee picker dropdown continues to show the `(Resigned)` / `（已離職）` suffix when the toggle is on.

#### Tests
- [x] `backend/tests/integration/test_employee_api.py::TestTerminateEmployee::test_terminated_employee_history_visible_in_reports` — Regression test: seed an EMPLOYEE, record an attendance log, terminate the employee, then verify `GET /api/reports/daily?emp_id=<that-id>` returns exactly one row containing the original summary. Confirms LSA-required history remains queryable.

#### Documentation
- [x] `CLAUDE.md` — Extended design decision #26 with the reports-compliance semantics (explicit-emp_id always honored; `include_terminated` toggle; ABSENT-generation guard for terminated employees).

### 14G: Self-Service Password Change -- DONE
Employees can change their own passwords after authentication. All old JWTs are immediately revoked by setting `password_changed_at`.
- [x] `backend/app/utils/password.py` — Added `validate_password_strength(password: str) -> bool` (enforces >=8 chars and >=1 digit)
- [x] `backend/app/schemas/auth.py` — Added `ChangePasswordRequest` schema (current_password, new_password with validation)
- [x] `backend/app/services/employee_service.py::change_password()` — Verifies current password, rejects new==current and new==emp_id, sets `password_changed_at` to now(UTC)
- [x] `backend/app/routers/auth.py` — Added `POST /api/auth/change-password` endpoint (authenticated users only)
- [x] `backend/app/middleware/auth_middleware.py` — Added `password_changed_at` revocation check: rejects any JWT whose `iat` predates the employee's most recent password change; backward compatible with employees whose `password_changed_at IS NULL` (allows legacy tokens)
- [x] `backend/tests/unit/test_change_password_service.py` — 6 tests (success, wrong current, unknown employee, terminated, new==current, new==emp_id)
- [x] `backend/tests/unit/test_change_password_schema.py` — 2 tests (valid/invalid password strength)
- [x] `backend/tests/integration/test_change_password_endpoint.py` — 10 tests (success with re-login, old JWT revoked, new JWT accepted, 401/422 error cases)
- [x] `backend/tests/integration/test_jwt_iat_revocation.py` — 3 tests (old JWT rejected, new JWT works, legacy employees still work)
- [x] `frontend/src/lib/validators.ts` — Added `changePasswordSchema` (current_password, new_password with strength validation)
- [x] `frontend/src/components/ChangePasswordForm.tsx` — Form with password strength meter, error/success feedback
- [x] `frontend/src/app/dashboard/change-password/page.tsx` — Dedicated change-password page linked from dashboard
- [x] `frontend/__tests__/unit/components/ChangePasswordForm.test.tsx` — 8 tests (form render, validation, API calls, success/error states)
- [x] `frontend/src/messages/en.json` / `zh.json` — Added i18n keys for change password form
- [x] Plan: `docs/superpowers/plans/2026-05-13-self-service-password-change.md`

## Phase 15: Org Reporting Hierarchy & Subtree-Scoped Authority -- IN PROGRESS

**Branch:** `feat/org-reporting-hierarchy`
**Goal:** A manager sees **only his own reports** (his reporting subtree), never the whole company and never a peer manager's team. Support org-chart depth (Manager → AVP → VP → President) without exploding the role enum.

**Design (confirmed 2026-06-16) — three axes kept separate:**
- **Capability** = existing 4-role enum `EMPLOYEE/MANAGER/HR/ADMIN`, **UNCHANGED**. AVP/VP/President are NOT new enum roles. (A flat role level says "how senior" but never "whose" — it can't express "the employees belonging to him." It also sidesteps the painful PG-enum migration documented under "Known Issues / Deferred" below.)
- **Scope** = new `employees.reports_to` tree. Manager authority = his own subtree (recursive walk of `reports_to`). HR/ADMIN = company-wide. Department label is display-only, **not** an authority mechanism. Two managers in the same department do NOT see each other's people.
- **Rank** = new `employees.rank` label (`MANAGER/AVP/VP/PRESIDENT`), a configurable ordered list in `system_config` key `ranks`. Display only — grants NO powers ("same powers, wider span"). Does not enforce tree shape.

**Rollout safety:** ship behind `system_config` toggle `org_scoping_enabled` (default **OFF** = current company-wide behavior preserved). HR populates the tree, verifies it, then flips ON — avoids an empty tree making every manager see nobody.

### 15A: ADMIN-creation escalation guard -- DONE (backend; 389 backend tests green)
On inspection the **frontend was already safe** and the **UPDATE path was already guarded**; the only real hole was the CREATE path at the API. Scope narrowed to a backend-only fix.
- [x] **No frontend change needed** — create form already hides ADMIN from non-admins (`admin/page.tsx:240`); edit form already wraps the *entire* role selector in `{isAdmin && (…)}` (`:296`), so HR can't change roles at all. My earlier "edit-form escalation gap" premise was a misread.
- [x] **UPDATE already guarded** — `employee_service.update_employee` raises `PermissionError`→403 when a non-`MANAGE_ROLES` caller sends any `role` field (`employee_service.py:109`). Left as-is.
- [x] **CREATE gap fixed** — `employee_service.create_employee(session, data, current_role)` now raises `PermissionError` when `data.role == ADMIN` and caller lacks `MANAGE_ROLES`. HR can still create EMPLOYEE/MANAGER/HR. Router threads `current_role` and maps `PermissionError`→403 (`routers/employees.py`).
- [x] `backend/tests/integration/test_employee_api.py` — HR creating ADMIN → 403 (+ not persisted); ADMIN creating ADMIN → 201; HR creating HR → 201.
- [x] `backend/tests/unit/test_employee_service.py` — service-level: HR→ADMIN raises `PermissionError` (nothing persisted); ADMIN→ADMIN succeeds. Updated 3 existing callers to the new signature.

### 15B: Data model + migration -- DONE (393 backend tests green)
- [x] `backend/app/models/employee.py` — added `reports_to: str | None` (self-FK→`employees.emp_id`, `ondelete="SET NULL"`, indexed) and `rank: str | None` (display label, no permissions).
- [x] Alembic migration `b8c9d0e1f2a3_add_reports_to_and_rank_to_employees.py` — chains off head `a7b8c9d0e1f2`; adds both nullable columns + index + self-FK. No backfill (`reports_to=NULL` = flat tree, behaves like today). Verified single linear head + valid offline Postgres DDL (`alembic upgrade … --sql`).
- [x] `backend/app/schemas/employee.py` — `EmployeeCreate` / `EmployeeResponse` / `EmployeeUpdate` round-trip `reports_to` + `rank` (both optional).
- [x] `backend/tests/unit/test_models.py` — persistence + self-reference + NULL defaults. `test_schemas.py` — round-trip + optional + response/update field presence.

### 15C: Ranks config + scoping toggle -- DONE (403 backend tests green)
- [x] `system_config_repository` — `get_ranks`/`set_ranks` (key `ranks`, value `{"ranks":[…]}`, default `["PRESIDENT","VP","AVP","MANAGER"]`) and `get_org_scoping_enabled`/`set_org_scoping_enabled` (key `org_scoping_enabled`, value `{"enabled":bool}`, default `False`).
- [x] `backend/app/schemas/org_hierarchy.py` — Ranks + OrgScoping request/response schemas.
- [x] `backend/app/routers/org_hierarchy.py` — `GET/PUT /api/admin/ranks` (GET any auth, PUT HR+) and `GET/PUT /api/admin/org-scoping` (GET any auth, **PUT ADMIN-only** — flipping it off restores company-wide visibility, so it's a system-level switch). Both registered in `main.py`.
- [x] `backend/tests/integration/test_org_config_api.py` (6) + `backend/tests/unit/test_system_config_ranks.py` (4) — defaults, role gates, round-trip.

### 15D: Authority engine -- TODO (unit-tested BEFORE wiring endpoints)
- [ ] `backend/app/repositories/employee_repository.py::get_subtree_emp_ids(session, root_emp_id) -> set[str]` — `WITH RECURSIVE` over `reports_to`, root inclusive, `UNION` (not `UNION ALL`) so a malformed cycle still terminates.
- [ ] Cycle/self-reference guard on write: `employee_service` rejects setting `reports_to` to self or to anyone inside the editee's subtree → 400.
- [ ] `backend/app/middleware/scope.py::resolve_scope(user, session) -> Scope` — HR/ADMIN = company-wide; MANAGER = own subtree; EMPLOYEE = {self}. Resolved from DB (JWT carries only `sub`+`role`, so no token change / no forced re-login). Honors `org_scoping_enabled` (off ⇒ company-wide for everyone, preserving current behavior).
- [ ] `backend/tests/unit/test_subtree.py` + `test_scope.py` — subtree correctness, cycle rejection, per-role scope, toggle off = company-wide.

### 15E: Endpoint enforcement -- TODO (TDD each: in-subtree pass / out-of-subtree 403 or filtered)
- [ ] `backend/app/routers/reports.py:64` — `GET /reports/daily`: filter to subtree emp_ids.
- [ ] `backend/app/routers/attendance.py:72` — `GET /attendance/team`: filter to subtree emp_ids.
- [ ] `backend/app/routers/attendance.py:174` — `POST /attendance/override`: target ∈ subtree else 403.
- [ ] `backend/app/routers/reasons.py:59` — `GET /reasons`: queried `emp_id` ∈ subtree else 403.
- [ ] `department` query param stays as an optional display filter *within* scope (not authority). HR/ADMIN unaffected (company-wide).
- [ ] `backend/tests/integration/` — for each endpoint: manager sees only own reports; out-of-subtree leak/forbidden cases; HR/ADMIN company-wide; toggle-off parity.

### 15F: Frontend -- TODO
- [ ] `frontend/src/app/admin/page.tsx` — employee create/edit forms (HR/ADMIN only): add `reports_to` selector (exclude editee's own subtree to prevent cycles) + `rank` dropdown (from `/api/admin/ranks`).
- [ ] `frontend/src/components/admin/RanksTab.tsx` — mirror `LeaveTypesTab.tsx` for the ordered ranks list.
- [ ] `frontend/src/app/team/page.tsx` + `reports/page.tsx` — a MANAGER's department picker constrained to his subtree (or read-only "my team" label); HR/ADMIN keep full picker.
- [ ] `frontend/src/types/index.ts` — add `reports_to` + `rank` to the Employee type.
- [ ] `frontend/src/messages/{en,zh}.json` — i18n keys (reports-to, rank, ranks management, org-scoping toggle).
- [ ] vitest — `reports_to`/`rank` selectors, `RanksTab`, scoped picker behavior.

### 15G: Docs -- TODO
- [ ] `CLAUDE.md` — new convention entry documenting the reporting-tree authority model (subtree scope, rank-as-label, `org_scoping_enabled` toggle, 4 scoped endpoints).
- [ ] Update "Known Issues / Deferred → Roles are hard-coded" note to point here (org depth now solved via the tree, so adding enum roles is no longer the answer for hierarchy).

### Non-goals (Phase 15)
- No multi-level approval workflow — authority = visibility + override over your subtree; overrides still take effect immediately (convention #20).
- Single boss per employee (one `reports_to`) — no matrix / dotted-line reporting.
- Rank grants no powers; export stays HR-only.

## Test Coverage Summary

| Layer | Tool | Actual / Est. | Target |
|-------|------|--------------|--------|
| Backend Unit | pytest | **201 passing** | 85% |
| Backend Integration | pytest + httpx | **69 passing** | 80% |
| Backend E2E | pytest | **5 passing** | Critical paths |
| Frontend Unit | vitest + testing-library | **68 passing** | 80% |
| Frontend E2E | Playwright | **33 stubs** (test.fixme) | Critical paths |
| **Total** | | **343 passing + 33 stubs** | **80%+** |

Note: Backend 275 (201 unit + 69 integration + 5 e2e). Frontend 68 (all green as of Phase 14B — repaired the 41 post-i18n/Phase-9C migration failures). Total code tests: 275 + 68 = 343.

## Known Issues / Deferred

### Roles are hard-coded (not HR-configurable)
Employee roles (`EMPLOYEE` / `MANAGER` / `HR` / `ADMIN`) are baked into the codebase at multiple layers. Unlike departments (stored in `system_config` and editable via admin UI), roles have no DB-backed list and adding/renaming requires a multi-file code change. Intentionally deferred — role names drive authorization logic throughout the codebase, so this is not a good candidate for runtime configuration.

**Surface area if we ever add or rename a role:**

- [ ] `backend/app/models/employee.py:10` — extend `Role(str, Enum)`
- [ ] New Alembic migration — PG enum requires `ALTER TYPE role ADD VALUE 'X'` or `ALTER TYPE role RENAME VALUE ...`; back up DB first (enum changes can't be cleanly rolled back once rows reference the value)
- [ ] `backend/app/services/permission_service.py` — add role to the frozenset permission matrix (without this, the role has no permissions)
- [ ] Audit `require_role(Role.X)` call sites across `backend/app/routers/{employees,reports,attendance,reasons,system_config}.py`, services, and `middleware/auth_middleware.py` — decide whether the new role satisfies each gate
- [ ] `backend/seed.py` + `backend/tests/` — fixtures and any role-literal assertions
- [ ] `frontend/src/types/index.ts:3` — extend `Role` union
- [ ] `frontend/src/app/admin/page.tsx:18` — add to `ROLE_LEVELS` hierarchy (pick numeric level)
- [ ] `frontend/src/app/admin/page.tsx:235-239` and `:298-302` — add `<option>` rows to create and edit dropdowns (respect `isAdmin` gating if applicable)
- [ ] `frontend/src/app/admin/page.tsx:342` — badge currently renders raw `emp.role`; swap to localized label if localized badges are desired
- [ ] `frontend/src/messages/en.json` / `zh.json` (lines 161-164) — add `roleX` i18n keys
- [ ] Frontend tests — any test constructing a user with a role literal

**Rename caveat:** renaming a role invalidates existing JWTs that encode the old role name — users must re-login.

**Decision:** only *adding* a new role is acceptable; renaming existing roles is out of scope (migration risks + JWT invalidation + ~11 files of string-literal references with no compile-time safety net).

**Open questions to answer before implementation:**

- [ ] **Role name** — the uppercase enum value stored in the DB (e.g. `AUDITOR`, `SUPERVISOR`, `VIEWER`)
- [ ] **Hierarchy position in `ROLE_LEVELS`** — current levels: `EMPLOYEE=1, MANAGER=2, HR=3, ADMIN=4`. New role's level? (And is it a *peer* of an existing role at the same numeric level but with different permissions, or does it sit between two existing levels?)
- [ ] **Permission set** — what can it do? Easiest framing: pick the closest existing role and describe the diff ("like MANAGER but can also view all attendance", "read-only HR", etc.), or enumerate against the existing capability axes: view own / view team / view all attendance, approve overrides, manage employees, export reports, change office location, refresh workday calendar, manage departments, manage grace period
- [ ] **i18n labels** — English label + 繁體中文 label for `frontend/src/messages/{en,zh}.json` (e.g. `"Auditor"` / `"稽核員"`)
- [ ] **Who can assign the role?** — HR-assignable (like MANAGER / HR today) or ADMIN-only (like ADMIN today, gated by `isAdmin` in `admin/page.tsx:239`)
