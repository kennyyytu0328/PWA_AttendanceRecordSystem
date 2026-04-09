# Remaining Manual Tests — 2026-03-20

41 test cases remaining. Check off as you go.

---

## Suite 1: Authentication (4 remaining)

- [ ] **TC-1.3**: Login with non-existent user (`GHOST99` / `anypass`) → same "Invalid credentials" error as wrong password
- [ ] **TC-1.5**: Rate limiting — fail login 5 times, 6th attempt returns "Too many login attempts" (429). Wait 60s, then login succeeds
- [ ] **TC-1.6**: Logout — click logout, verify redirect to `/login`, token removed from localStorage, can't access `/dashboard` directly
- [ ] **TC-1.7**: Token expiry — wait 30min (or set `ACCESS_TOKEN_EXPIRE_MINUTES=1` in `.env`), verify protected pages redirect to login

## Suite 2: Punch (3 remaining)

- [ ] **TC-2.4**: Low accuracy warning — use DevTools > Sensors, set accuracy to 500m+, punch → amber "Low Accuracy" warning shown
- [ ] **TC-2.5**: Punch without auth — clear localStorage, navigate to `/punch` → redirected to `/login`
- [ ] **TC-2.6**: Verify punch in today's logs — after a successful punch, go to `/dashboard` (punch count incremented) and `/attendance` (entry in table)

## Suite 3: Attendance History (1 remaining)

- [ ] **TC-3.4**: Override indicator — have a manager override a punch (TC-5.3), then view as the employee → amber "Overridden" badge on the entry

## Suite 4: Dashboard (3 remaining)

- [ ] **TC-4.2**: Login as `MGR01` → dashboard shows "Punch", "Attendance History", **"Team Attendance"** links
- [ ] **TC-4.4**: Login as `ADMIN01` → dashboard shows all links including **"Admin Panel"**
- [ ] **TC-4.5**: Loading state — on dashboard, verify skeleton/pulse animation appears briefly while data loads

## Suite 5: Role-Based Access Control (6 remaining)

- [ ] **TC-5.1**: Login as `EMP01`, use API tool (curl/Postman) to hit these endpoints with token:
  - `GET /api/attendance/team?date=2026-03-19` → 403
  - `GET /api/attendance/all?date=2026-03-19` → 403
  - `POST /api/employees` → 403
  - `DELETE /api/employees/EMP02` → 403
  - `GET /api/reports/daily?date=2026-03-19` → 403
  - `PUT /api/config/office-location` → 403

- [ ] **TC-5.2**: Login as `MGR01`, verify:
  - `GET /api/attendance/team?date=2026-03-19` → 200
  - `GET /api/attendance/all?date=2026-03-19` → 403
  - `GET /api/reports/daily?date=2026-03-19` → 200
  - `GET /api/reports/export?format=json&start_date=2026-03-01&end_date=2026-03-19` → 403
  - `POST /api/reports/generate?date=2026-03-19` → 403

- [ ] **TC-5.3**: Login as `MGR01`, `POST /api/attendance/override` targeting `EMP01` → 200, response has `is_overridden: true`

- [ ] **TC-5.5**: Login as `ADMIN01`, verify:
  - `POST /api/reports/generate?date=2026-03-19` → 200
  - `DELETE /api/employees/EMP02` → 200
  - `GET /api/config/some-key` → 200
  - `PUT /api/config/some-key` → 200

- [ ] **TC-5.6**: Employee list visibility:
  - `EMP01` → `GET /api/employees` → only sees own record
  - `MGR01` → sees Engineering department only
  - `HR01` → sees all employees
  - `ADMIN01` → sees all employees

- [ ] **TC-5.7**: Self-update vs cross-update:
  - `EMP01` → `PUT /api/employees/EMP01` with `{"name":"New Name"}` → 200
  - `EMP01` → `PUT /api/employees/EMP01` with `{"role":"ADMIN"}` → 403
  - `EMP01` → `PUT /api/employees/EMP02` with `{"name":"Hacked"}` → 403

## Suite 6: Admin Panel UI (2 remaining)

- [ ] **TC-6.1**: Login as `EMP01`, navigate to `/admin` → "Access Denied" message, no admin sections
- [ ] **TC-6.3**: Login as `ADMIN01`, navigate to `/admin` → all 3 sections visible (Employee Management, Office Location, **System Config**)

## Suite 7: Reports (4 remaining)

- [ ] **TC-7.1**: Login as `ADMIN01`, `POST /api/reports/generate?date=2026-03-19` → 200, `generated_count` > 0
- [ ] **TC-7.2**: Login as `MGR01`, `GET /api/reports/daily?date=2026-03-19` → 200, array of summary records with emp_id, date, status
- [ ] **TC-7.3**: Login as `HR01`, `GET /api/reports/export?format=csv&start_date=2026-03-01&end_date=2026-03-19` → 200, Content-Type: text/csv, valid CSV content
- [ ] **TC-7.4**: Login as `HR01`, `GET /api/reports/export?format=json&start_date=2026-03-01&end_date=2026-03-19` → 200, JSON array

## Suite 8: System Config (3 remaining)

- [ ] **TC-8.1**: Login as `EMP01`, `GET /api/config/office-location` → 200 (any user can read)
- [ ] **TC-8.3**: Login as `EMP01`, `PUT /api/config/office-location` → 403 (can't write)
- [ ] **TC-8.4**: Login as `ADMIN01`, `PUT /api/config/maintenance_mode` with `{"value": true}` → 200, then `GET /api/config/maintenance_mode` → returns the value

## Suite 9: Security (6 remaining)

- [ ] **TC-9.1**: SQL injection — `POST /api/auth/login` with `emp_id: "'; DROP TABLE employees;--"` → 401, verify employees table still intact
- [ ] **TC-9.2**: XSS — create employee with name `<script>alert('xss')</script>`, view in admin panel → script rendered as text, not executed
- [ ] **TC-9.3**: Security headers — make any API request, check response headers in DevTools:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `Content-Security-Policy: default-src 'self'`
- [ ] **TC-9.4**: CORS — make API request from `http://localhost:3000` → allowed. From other origins → blocked
- [ ] **TC-9.5**: Invalid JWT — `GET /api/auth/me` with `Authorization: Bearer invalid-token` → 401. With expired token → 401. With wrong-secret token → 401
- [ ] **TC-9.6**: No user enumeration — login with wrong password vs non-existent user → identical "Invalid credentials" message and similar response time

## Suite 10: PWA (3 remaining)

- [ ] **TC-10.1**: DevTools > Application > Manifest → name "GoGoFresh Attendance", display "standalone", icons 192 + 512
- [ ] **TC-10.2**: Inspect page source → `<meta name="theme-color" content="#10b981">`
- [ ] **TC-10.3**: Mobile responsiveness — DevTools mobile mode → punch button centered, tables scroll, login form fits screen

## Suite 11: E2E Workflows (3 remaining)

- [ ] **TC-11.1**: Full onboarding — login as ADMIN → create HR user via API → HR logs in → HR creates EMPLOYEE → new employee logs in and punches
- [ ] **TC-11.2**: Full daily cycle — HR sets office location → employee punches in (morning) → punches out (evening) → check `/attendance` shows 2 entries → ADMIN generates summary → MANAGER views report → HR exports CSV
- [ ] **TC-11.3**: Manager override — employee misses a punch → manager creates override via `POST /api/attendance/override` → employee sees overridden entry in attendance history

---

**Total: 41 test cases**

### Quick API Auth Cheat Sheet

```bash
# Login and get token
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"emp_id":"EMP01","password":"emp12345"}' | jq .access_token

# Use token in requests
curl -s http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <TOKEN>"
```

| User | Password | Role |
|------|----------|------|
| ADMIN01 | admin123 | ADMIN |
| HR01 | hr123456 | HR |
| MGR01 | mgr12345 | MANAGER |
| EMP01 | emp12345 | EMPLOYEE |
| EMP02 | emp12345 | EMPLOYEE |
