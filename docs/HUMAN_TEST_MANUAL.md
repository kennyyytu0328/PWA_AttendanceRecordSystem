# GoGoFresh Attendance System — Human Test Manual

## Prerequisites

### Environment Setup

1. Start backend:
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```
2. Start frontend:
   ```bash
   cd frontend
   npm run dev
   ```
3. Start PostgreSQL (or use Docker):
   ```bash
   docker-compose up db -d
   ```
4. Run migrations:
   ```bash
   cd backend && alembic upgrade head
   ```

### Seed Data

Create test users via API (use curl, Postman, or the admin panel once an ADMIN exists):

| emp_id | password | role | department |
|--------|----------|------|------------|
| ADMIN01 | admin123 | ADMIN | IT |
| HR01 | hr123456 | HR | HR |
| MGR01 | mgr12345 | MANAGER | Engineering |
| EMP01 | emp12345 | EMPLOYEE | Engineering |
| EMP02 | emp12345 | EMPLOYEE | Sales |

### Tools Needed

- Browser (Chrome/Edge recommended for WebAuthn support)
- Browser DevTools (Network tab, Console, Application tab)
- API testing tool (curl / Postman / httpie) for backend-only tests

---

## Test Suite 1: Authentication

### TC-1.1: Login with valid credentials

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open `http://localhost:3000/login` | Login form with Employee ID and Password fields |
| 2 | Enter `EMP01` in Employee ID field | Field accepts input |
| 3 | Enter `emp12345` in Password field | Field accepts input (masked) |
| 4 | Click "Sign In" button | Loading spinner appears on button |
| 5 | Wait for redirect | Redirected to dashboard (`/`) |
| 6 | Check browser DevTools > Application > Local Storage | `access_token` key exists with JWT value |

### TC-1.2: Login with wrong password

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open `/login` | Login form displayed |
| 2 | Enter `EMP01` / `wrongpass` | Fields accept input |
| 3 | Click "Sign In" | Error message: "Invalid credentials" (red alert) |
| 4 | Verify no redirect occurs | Still on `/login` page |

### TC-1.3: Login with non-existent user

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter `GHOST99` / `anypass` on login page | Fields accept input |
| 2 | Click "Sign In" | Error message: "Invalid credentials" |
| 3 | Verify error is identical to TC-1.2 | Same message — no user enumeration |

### TC-1.4: Login with empty fields

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Leave both fields empty, click "Sign In" | Validation error displayed |
| 2 | Enter Employee ID only, click "Sign In" | Password validation error |

### TC-1.5: Rate limiting (5 failed attempts)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter `EMP01` / `wrong` and click "Sign In" 5 times | Each attempt shows "Invalid credentials" |
| 2 | Attempt 6th login with `EMP01` / `wrong` | Error: "Too many login attempts. Please try again later." (HTTP 429) |
| 3 | Wait 60 seconds | Rate limit window expires |
| 4 | Attempt login with correct password `emp12345` | Login succeeds |

### TC-1.6: Logout

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as any user | Dashboard displayed |
| 2 | Click logout button | Redirected to `/login` |
| 3 | Check Local Storage | `access_token` removed |
| 4 | Navigate to `/dashboard` directly | Redirected to `/login` |

### TC-1.7: Token expiry

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login and note the time | Token issued |
| 2 | Wait 30+ minutes (or set `ACCESS_TOKEN_EXPIRE_MINUTES=1` in .env) | Token expires |
| 3 | Try accessing a protected page | Redirected to login or 401 error |

---

## Test Suite 2: Punch (Clock In/Out)

### TC-2.1: Successful punch (office — WFO)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` | Dashboard shown |
| 2 | Navigate to `/punch` | Punch page with large circular button |
| 3 | Browser asks for location permission | Allow location access |
| 4 | Click the Punch button | Loading spinner appears, button disabled |
| 5 | Wait for result | Result card shows: Work Mode = **WFO**, distance in km |
| 6 | Verify distance is < 0.1 km (if at office) | Shows as WFO (within 100m threshold) |

### TC-2.2: Successful punch (remote — WFH)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` | Dashboard shown |
| 2 | Use Chrome DevTools > Sensors to override location to a far-away point | Location overridden |
| 3 | Navigate to `/punch`, click Punch button | Result shows Work Mode = **WFH**, distance > 0.1 km |

### TC-2.3: Geolocation denied

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to `/punch` | Punch page displayed |
| 2 | Block location permission in browser settings | Permission denied |
| 3 | Click Punch button | Error message about location permission |

### TC-2.4: Low accuracy warning

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Use DevTools Sensors to set accuracy to 500m+ | Low accuracy simulated |
| 2 | Click Punch button | Result includes amber "Low Accuracy" warning |

### TC-2.5: Punch without authentication

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Clear Local Storage (remove token) | Token removed |
| 2 | Navigate to `/punch` | Redirected to `/login` |

### TC-2.6: Verify punch appears in today's logs

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete a successful punch (TC-2.1) | Punch recorded |
| 2 | Navigate to `/dashboard` | Today's stats show punch count incremented |
| 3 | Navigate to `/attendance` | Today's date has the punch entry in the table |

---

## Test Suite 3: Attendance History

### TC-3.1: View own attendance records

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` | Dashboard shown |
| 2 | Navigate to `/attendance` | Attendance History page with heading |
| 3 | Verify table columns | Date, Time, Work Mode, Location, Status columns |
| 4 | Check records belong to `EMP01` only | No other employee's records shown |

### TC-3.2: Date range filtering

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | On Attendance History page, set Start Date to 7 days ago | Date filter applied |
| 2 | Set End Date to today | Date range set |
| 3 | Verify only records within range are shown | Filtered results |
| 4 | Set dates to a range with no records | "No attendance records found" empty state |

### TC-3.3: Work mode badges

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | View records with WFO entries | Blue "WFO" badge with building icon |
| 2 | View records with WFH entries | Green "WFH" badge with home icon |

### TC-3.4: Override indicator

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Have a manager override a punch (see TC-5.3) | Override created |
| 2 | View attendance as the overridden employee | Amber "Overridden" badge on the entry |

---

## Test Suite 4: Dashboard

### TC-4.1: Dashboard content for EMPLOYEE

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` | Dashboard displayed |
| 2 | Check welcome message | Shows employee ID |
| 3 | Check stats cards | Today's punch count, current work mode |
| 4 | Check navigation links | "Punch" and "Attendance History" visible |
| 5 | Verify NO team/admin links | No Team Attendance, Reports, or Config links |

### TC-4.2: Dashboard content for MANAGER

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `MGR01` | Dashboard displayed |
| 2 | Check navigation links | "Punch", "Attendance History", **"Team Attendance"** visible |
| 3 | Verify no admin-only links | No Reports or Config links |

### TC-4.3: Dashboard content for HR

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `HR01` | Dashboard displayed |
| 2 | Check navigation links | All from MANAGER + **"Reports"** visible |

### TC-4.4: Dashboard content for ADMIN

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `ADMIN01` | Dashboard displayed |
| 2 | Check navigation links | All links visible including **"System Config"** |

### TC-4.5: Loading state

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login and navigate to dashboard | Skeleton/pulse animation while data loads |
| 2 | Wait for data | Skeleton replaced with actual content |

---

## Test Suite 5: Role-Based Access Control

### TC-5.1: EMPLOYEE cannot access team endpoints

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01`, get token | Token obtained |
| 2 | `GET /api/attendance/team?date=2026-03-19` with token | **403 Forbidden** |
| 3 | `GET /api/attendance/all?date=2026-03-19` with token | **403 Forbidden** |
| 4 | `POST /api/employees` with token | **403 Forbidden** |
| 5 | `DELETE /api/employees/EMP02` with token | **403 Forbidden** |
| 6 | `GET /api/reports/daily?date=2026-03-19` with token | **403 Forbidden** |
| 7 | `PUT /api/config/office-location` with token | **403 Forbidden** |

### TC-5.2: MANAGER access boundaries

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `MGR01`, get token | Token obtained |
| 2 | `GET /api/attendance/team?date=2026-03-19` | **200 OK** — team logs |
| 3 | `GET /api/attendance/all?date=2026-03-19` | **403 Forbidden** |
| 4 | `GET /api/reports/daily?date=2026-03-19` | **200 OK** |
| 5 | `GET /api/reports/export?format=json&start_date=...&end_date=...` | **403 Forbidden** |
| 6 | `POST /api/reports/generate?date=2026-03-19` | **403 Forbidden** |

### TC-5.3: Manager override

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `MGR01` | Token obtained |
| 2 | `POST /api/attendance/override` with `EMP01` as target | **200 OK** — overridden log created |
| 3 | Verify response has `is_overridden: true` | Override flag set |

### TC-5.4: HR full access

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `HR01` | Token obtained |
| 2 | `GET /api/attendance/all?date=2026-03-19` | **200 OK** |
| 3 | `POST /api/employees` (create new employee) | **201 Created** |
| 4 | `PUT /api/config/office-location` | **200 OK** |
| 5 | `GET /api/reports/export?format=csv&start_date=...&end_date=...` | **200 OK** with CSV |
| 6 | `POST /api/reports/generate?date=2026-03-19` | **403 Forbidden** (ADMIN only) |
| 7 | `DELETE /api/employees/EMP02` | **403 Forbidden** (ADMIN only) |

### TC-5.5: ADMIN full access

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `ADMIN01` | Token obtained |
| 2 | `POST /api/reports/generate?date=2026-03-19` | **200 OK** |
| 3 | `DELETE /api/employees/EMP02` | **200 OK** |
| 4 | `GET /api/config/some-key` | **200 OK** |
| 5 | `PUT /api/config/some-key` | **200 OK** |

### TC-5.6: Employee list visibility

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01`, `GET /api/employees` | Only sees own record |
| 2 | Login as `MGR01`, `GET /api/employees` | Sees Engineering department only |
| 3 | Login as `HR01`, `GET /api/employees` | Sees all employees |
| 4 | Login as `ADMIN01`, `GET /api/employees` | Sees all employees |

### TC-5.7: Self-update vs cross-update

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` | Token obtained |
| 2 | `PUT /api/employees/EMP01` with `{ "name": "New Name" }` | **200 OK** — name updated |
| 3 | `PUT /api/employees/EMP01` with `{ "role": "ADMIN" }` | **403 Forbidden** — can't change own role |
| 4 | `PUT /api/employees/EMP02` with `{ "name": "Hacked" }` | **403 Forbidden** — can't update others |

---

## Test Suite 6: Admin Panel (UI)

### TC-6.1: Access denied for EMPLOYEE

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` | Dashboard shown |
| 2 | Navigate to `/admin` | "Access Denied" message displayed |
| 3 | Verify no admin sections visible | No employee list, no config forms |

### TC-6.2: HR sees employee management + office location

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `HR01` | Dashboard shown |
| 2 | Navigate to `/admin` | Admin panel heading displayed |
| 3 | Verify "Employee Management" section | Employee table with ID, Name, Department, Role, Shift |
| 4 | Verify "Office Location" section | Latitude/Longitude input fields + Update button |
| 5 | Verify no "System Config" section | Section not visible for HR |

### TC-6.3: ADMIN sees all sections

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `ADMIN01` | Dashboard shown |
| 2 | Navigate to `/admin` | All three sections visible |
| 3 | Verify "System Config" section | Config entries displayed with key/value pairs |

### TC-6.4: Update office location via UI

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `HR01`, go to `/admin` | Admin panel shown |
| 2 | Enter latitude `25.033` and longitude `121.565` | Fields accept valid numbers |
| 3 | Click "Update" button | Success message displayed |
| 4 | Refresh page | Values persist (fetched from API) |

---

## Test Suite 7: Reports

### TC-7.1: Generate daily summaries (ADMIN)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `ADMIN01` | Token obtained |
| 2 | Ensure some punch data exists for today | Prerequisite |
| 3 | `POST /api/reports/generate?date=2026-03-19` | **200 OK**, `generated_count` > 0 |

### TC-7.2: View daily report (MANAGER)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `MGR01` | Token obtained |
| 2 | `GET /api/reports/daily?date=2026-03-19` | **200 OK** — array of summary records |
| 3 | Verify fields: emp_id, date, first_in, last_out, status | All present |

### TC-7.3: Export as CSV (HR)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `HR01` | Token obtained |
| 2 | `GET /api/reports/export?format=csv&start_date=2026-03-01&end_date=2026-03-19` | **200 OK** |
| 3 | Check `Content-Type` header | `text/csv` |
| 4 | Check `Content-Disposition` header | Contains `attachment` and filename |
| 5 | Verify CSV content has header row + data rows | Valid CSV format |

### TC-7.4: Export as JSON (HR)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `HR01` | Token obtained |
| 2 | `GET /api/reports/export?format=json&start_date=2026-03-01&end_date=2026-03-19` | **200 OK** — JSON array |

---

## Test Suite 8: System Configuration

### TC-8.1: Get office location (any user)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` | Token obtained |
| 2 | `GET /api/config/office-location` | **200 OK** — returns current location or null |

### TC-8.2: Set office location (HR)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `HR01` | Token obtained |
| 2 | `PUT /api/config/office-location` with `{ "latitude": 25.033, "longitude": 121.565 }` | **200 OK** |
| 3 | `GET /api/config/office-location` | Returns the values just set |

### TC-8.3: EMPLOYEE cannot set office location

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `EMP01` | Token obtained |
| 2 | `PUT /api/config/office-location` with body | **403 Forbidden** |

### TC-8.4: Generic config CRUD (ADMIN)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `ADMIN01` | Token obtained |
| 2 | `PUT /api/config/maintenance_mode` with `{ "value": true }` | **200 OK** |
| 3 | `GET /api/config/maintenance_mode` | Returns `{ "key": "maintenance_mode", "value": true }` |

---

## Test Suite 9: Security

### TC-9.1: SQL injection prevention

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | `POST /api/auth/login` with `emp_id: "'; DROP TABLE employees;--"` | **401** — treated as literal string, no DB damage |
| 2 | Verify employees table still exists | Table intact |

### TC-9.2: XSS prevention

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create employee with name `<script>alert('xss')</script>` | Accepted as literal string |
| 2 | View employee in admin panel | Script tags rendered as text, not executed |

### TC-9.3: Security headers present

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Make any API request | Check response headers in DevTools |
| 2 | Verify `X-Content-Type-Options: nosniff` | Present |
| 3 | Verify `X-Frame-Options: DENY` | Present |
| 4 | Verify `X-XSS-Protection: 1; mode=block` | Present |
| 5 | Verify `Strict-Transport-Security` header | Present |
| 6 | Verify `Content-Security-Policy: default-src 'self'` | Present |

### TC-9.4: CORS enforcement

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Make API request from `http://localhost:3000` | **Allowed** |
| 2 | Make API request from `http://evil.com` (via curl with Origin header) | **Blocked** — no CORS headers in response |

### TC-9.5: Invalid/expired JWT rejected

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | `GET /api/auth/me` with `Authorization: Bearer invalid-token` | **401 Unauthorized** |
| 2 | `GET /api/auth/me` with expired token | **401 Unauthorized** |
| 3 | `GET /api/auth/me` with token signed by wrong secret | **401 Unauthorized** |

### TC-9.6: No user enumeration

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login with existing user + wrong password | "Invalid credentials" |
| 2 | Login with non-existent user + any password | "Invalid credentials" (identical message) |
| 3 | Compare response time of both | Should be similar (no timing leak) |

---

## Test Suite 10: PWA

### TC-10.1: Web App Manifest

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open DevTools > Application > Manifest | Manifest loaded |
| 2 | Verify `name`: "GoGoFresh Attendance" | Correct |
| 3 | Verify `display`: "standalone" | Correct |
| 4 | Verify icons: 192x192 and 512x512 entries | Present |

### TC-10.2: Theme color

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Inspect `<meta name="theme-color">` in page source | Value: `#10b981` |

### TC-10.3: Mobile responsiveness

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open app on mobile device or DevTools mobile mode | Responsive layout |
| 2 | Check punch button is centered and tappable | Large touch target (48x48+ pixels) |
| 3 | Check tables scroll horizontally if needed | No content overflow |
| 4 | Check login form fits mobile screen | Fields full-width, button accessible |

---

## Test Suite 11: End-to-End Workflows

### TC-11.1: Full employee onboarding

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as `ADMIN01` | Dashboard shown |
| 2 | Create HR user via `POST /api/employees` | **201 Created** |
| 3 | Login as the new HR user | Login succeeds |
| 4 | Create EMPLOYEE via `POST /api/employees` | **201 Created** |
| 5 | New employee logs in | Login succeeds, dashboard shows |
| 6 | New employee punches | Punch recorded successfully |

### TC-11.2: Full daily attendance cycle

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | HR sets office location | Location saved |
| 2 | Employee punches in (morning, at office) | WFO punch recorded |
| 3 | Employee punches out (evening, at office) | Second WFO punch recorded |
| 4 | Check `/attendance` — 2 entries for today | Both punches visible |
| 5 | ADMIN generates daily summary | Summary created |
| 6 | MANAGER views daily report | Shows first-in, last-out, status |
| 7 | HR exports CSV for the date range | CSV contains the data |

### TC-11.3: Manager override workflow

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Employee forgets to punch | No punch record |
| 2 | Manager creates override for the employee | Override log with `is_overridden: true` |
| 3 | Employee views attendance | Sees overridden entry with indicator |

---

## Quick Reference: API Error Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | Success | Normal response |
| 201 | Created | Employee/resource created |
| 400 | Bad Request | Invalid input, business logic error |
| 401 | Unauthorized | Missing/invalid/expired token, wrong credentials |
| 403 | Forbidden | Insufficient role permissions |
| 404 | Not Found | Employee/resource doesn't exist |
| 422 | Unprocessable | Pydantic validation failure (missing/invalid fields) |
| 429 | Too Many Requests | Rate limit exceeded (5 attempts/min on login) |

## Quick Reference: Role Hierarchy

```
ADMIN (full access)
  |
  HR (employees, reports, office location)
  |
  MANAGER (team attendance, overrides, daily reports)
  |
  EMPLOYEE (own attendance, punch)
```

Each higher role inherits ALL permissions from lower roles.
