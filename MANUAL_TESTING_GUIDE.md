# Manual Testing Guide — GoGoFresh Attendance System

## Prerequisites

### 1. Start Services

#### Option A: Docker Compose — full stack

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
```

#### Option B: DB in Docker, backend + frontend on host (recommended for active dev)

**Terminal 1 — Database (Docker):**
```bash
docker compose up -d db
```
DB exposed on host port **5433** (compose maps `5433:5432`). Backend `.env` must use `localhost:5433`.

**Terminal 2 — Backend (host venv):**

First-time setup (Windows / PowerShell):
```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" sqlmodel asyncpg alembic webauthn "passlib[bcrypt]" "python-jose[cryptography]" pydantic-settings python-multipart aiosqlite openpyxl pytest pytest-asyncio httpx freezegun factory-boy coverage pytest-cov
pip install "bcrypt<4.1"   # passlib is incompatible with bcrypt>=5.0
copy .env.example .env     # then edit DATABASE_URL → localhost:5433
alembic upgrade head
```

Daily use:
```powershell
cd backend
.\.venv\Scripts\Activate.ps1   # prepends .venv\Scripts to PATH for this shell
python -m uvicorn app.main:app --reload --port 8000
```

> **Why activate?** When you type `python`, Windows uses the first `python.exe` on PATH — by default that's the system Python (`C:\Python314\python.exe`), which has none of the project deps. Activating prepends `.venv\Scripts\` so `python` resolves to the venv copy. Verify with `where python` (first line wins). Alternatively, skip activation and call `.\.venv\Scripts\python.exe -m uvicorn ...` explicitly.

**Terminal 3 — Frontend:**
```bash
cd frontend
npm install   # first time only
npm run dev
```

### 2. Seed Test Data

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python seed.py
```

### 3. URLs

| Service  | URL                    |
|----------|------------------------|
| Frontend | http://localhost:3000   |
| Backend  | http://localhost:8000   |
| API Docs | http://localhost:8000/docs |

### 4. Test Accounts

| ID      | Role     | Password   | Department  |
|---------|----------|------------|-------------|
| ADMIN01 | ADMIN    | admin123   | IT          |
| HR01    | HR       | hr123456   | HR          |
| MGR01   | MANAGER  | mgr12345   | Engineering |
| EMP01   | EMPLOYEE | emp12345   | Engineering |
| EMP02   | EMPLOYEE | emp12345   | Sales       |

All accounts have shift: **09:00 — 18:00**.

---

## Test 1: Login & Authentication

### 1.1 Password Login

1. Open http://localhost:3000
2. Enter Employee ID: `EMP01`, Password: `emp12345`
3. Click **Sign in**
4. **Expected**: Redirect to `/dashboard`, welcome message shows "EMP01"

### 1.2 Invalid Login

1. Enter Employee ID: `EMP01`, Password: `wrongpass`
2. Click **Sign in**
3. **Expected**: Error message appears, no redirect

### 1.3 Fingerprint Login Without Registration (Expected Failure)

> **Important**: Fingerprint login requires registration first. Attempting to use it before registering will fail.

1. On Login page, enter Employee ID: `EMP01`
2. Click **Sign in with Fingerprint**
3. **Expected**: Error message appears (backend returns 400 "no registered device")
4. Browser console shows: `POST /api/auth/authenticate/generate-options 400`
5. This is correct behavior — the employee has not registered a fingerprint yet

### 1.4 WebAuthn / Fingerprint Registration

> **You must log in with password first**, then register fingerprint from the Dashboard.

1. Log in as `EMP01` via password (Test 1.1)
2. On Dashboard, find the **Fingerprint** section
3. Click **Register Fingerprint**
4. Complete the biometric prompt (Windows Hello / Touch ID / Security Key)
5. **Expected**: Success message "Fingerprint registered successfully!"

### 1.5 WebAuthn / Fingerprint Login (After Registration)

1. Log out (clear localStorage or use a new incognito window)
2. On Login page, enter Employee ID: `EMP01`
3. Click **Sign in with Fingerprint**
4. Complete the biometric prompt
5. **Expected**: Redirect to `/dashboard`

### 1.6 Remove Fingerprint

1. Log in as `EMP01`
2. On Dashboard, find the **Fingerprint** section (should show "Fingerprint already registered")
3. Click **Remove Fingerprint**
4. **Expected**: "Fingerprint removed successfully"
5. Attempting fingerprint login again should now fail (same as Test 1.3)

---

## Test 2: Office Location Setup (HR/ADMIN)

> **Must complete before punch tests.** Without this, punching will fail with "Office location not configured".

1. Log in as `HR01`
2. Go to **Admin Panel** (`/admin`)
3. In the **Office Location** section, enter:
   - Latitude: `24.786930` (ITRI Hsinchu)
   - Longitude: `120.997765`
4. Click **Update Location**
5. **Expected**: "Office location updated successfully"

### Alternative — via API

```bash
curl -X PUT http://localhost:8000/api/config/office-location \
  -H "Authorization: Bearer <HR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"latitude": 24.786930, "longitude": 120.997765}'
```

---

## Test 3: Grace Period Configuration (HR/ADMIN)

1. Log in as `HR01`
2. Go to **Admin Panel** (`/admin`)
3. Find the **Grace Period** section (amber timer icon)
4. **Expected**: Current value shows `5` (default)
5. Change to `10`, click **Update Grace Period**
6. **Expected**: "Grace period updated successfully"
7. Change back to `5` for subsequent tests

### Verify via API

```bash
curl http://localhost:8000/api/config/grace-period \
  -H "Authorization: Bearer <TOKEN>"
# Expected: {"minutes": 5}
```

---

## Test 4: Punch — Normal (On Time)

> For this test, you need to punch **between 09:00 and 09:05** (within grace period).
> If testing outside these hours, temporarily adjust the employee's shift times in Admin Panel.

1. Log in as `EMP01`
2. Go to **Punch** (`/punch`)
3. Allow location access when the browser prompts
4. Click the large **Punch** button
5. **Expected**:
   - Green "Punch Recorded" card appears
   - Work Mode shows `OFFICE` (if within 2km of configured office) or `WFH`
   - Distance in km is shown
   - **No** tardiness alert (no red/amber banner)

---

## Test 5: Punch — Late (Tardiness Alert + Reason Submission)

> To simulate being late: either test after 09:05, or set the employee's shift start to a time in the past.

### 5.1 Setup — Adjust Shift Time

1. Log in as `HR01` or `ADMIN01`
2. Go to **Admin Panel** → Employee list
3. Click edit (pencil) on `EMP01`
4. Set **Shift Start** to a time that makes the current time "late" (e.g., if it's 14:30 now, set shift start to `14:00`)
5. Save

### 5.2 Punch as Late Employee

1. Log in as `EMP01`
2. Go to **Punch** (`/punch`)
3. Click the **Punch** button
4. **Expected**:
   - Green "Punch Recorded" card
   - **Red alert banner**: "You are late. Please submit a reason below." (EN) / "您已遲到，請在下方填寫原因。" (ZH)
   - A **textarea** appears below the alert with a "Submit Reason" button

### 5.3 Submit Reason

1. Type a reason in the textarea: `Traffic jam on highway`
2. Click **Submit Reason**
3. **Expected**: Green confirmation "Reason submitted successfully"
4. The textarea disappears, replaced by the success message

### 5.4 Verify Reason Persisted

```bash
curl http://localhost:8000/api/reasons/me \
  -H "Authorization: Bearer <EMP01_TOKEN>"
# Expected: JSON array with the submitted reason
```

---

## Test 6: Punch — Early Leave

### 6.1 Setup

1. As HR/ADMIN, set `EMP01`'s shift end to a future time (e.g., `23:00`)
2. Make sure `EMP01` already has at least one punch today (from Test 5)

### 6.2 Punch Again

1. Log in as `EMP01`, go to **Punch**, click the button
2. **Expected**:
   - **Amber alert banner**: "You are leaving early. Please submit a reason below."
   - Reason textarea appears
3. Submit a reason: `Doctor appointment`
4. **Expected**: Success confirmation

### 6.3 Reset Shift Times

1. As HR/ADMIN, reset `EMP01`'s shift back to `09:00 — 18:00`

---

## Test 7: Employee Management (HR/ADMIN)

### 7.1 Create Employee

1. Log in as `HR01`
2. Go to **Admin Panel**
3. Click **Add Employee**
4. Fill in:
   - ID: `EMP03`
   - Name: `Charlie Test`
   - Department: `Engineering`
   - Role: `EMPLOYEE`
   - Password: `emp12345`
   - Shift: `08:30 — 17:30` (custom shift)
5. Click **Create**
6. **Expected**: "Employee created", new row in table with shift `08:30 - 17:30`

### 7.2 Edit Employee Shift

1. Click edit (pencil) on `EMP03`
2. Change **Shift Start** to `09:30`, **Shift End** to `18:30`
3. Click **Save**
4. **Expected**: "{EMP03} updated", table row shows `09:30 - 18:30`

### 7.3 Verify Per-Employee Shift

1. Log in as `EMP03` (password: `emp12345`)
2. Punch at a time that is on-time for 09:30 but would be late for 09:00
3. **Expected**: No tardiness alert (the system uses EMP03's personal 09:30 shift, not a global setting)

---

## Test 8: Reports — Daily Report

### 8.1 View Report

1. Log in as `MGR01` (MANAGER)
2. Go to **Reports** (`/reports`)
3. Set date range to today
4. **Expected**: Table shows summaries for employees who punched today (from Tests 4-6)

### 8.2 Filter by Department

1. Select department: `Engineering`
2. **Expected**: Only Engineering employees shown (EMP01, MGR01, EMP03)

### 8.3 Filter by Employee

1. Select employee: `EMP01 - Alice Engineer`
2. **Expected**: Only EMP01's records shown

### 8.4 Filter by Status

1. Clear employee filter, select status: `LATE`
2. **Expected**: Only rows with LATE status shown

---

## Test 9: Export — CSV, JSON, Excel

> Requires HR+ role.

### 9.1 Generate Summaries First

1. Log in as `ADMIN01`
2. Go to **Reports** → **Generate Summaries** section
3. Set date to today, click **Generate**
4. **Expected**: "N summaries generated"

### 9.2 CSV Export

1. Log in as `HR01`
2. In the **Export Data** section:
   - Set date range to today
   - Format: `CSV`
3. Click **Export**
4. **Expected**: `.csv` file downloads. Open it — columns: emp_id, name, department, date, first_clock_in, last_clock_out, status

### 9.3 JSON Export

1. Change format to `JSON`, click **Export**
2. **Expected**: `.json` file downloads with same data

### 9.4 Excel Export

1. Change format to `Excel`, click **Export**
2. **Expected**: `.xlsx` file downloads
3. Open in Excel/LibreOffice — verify:
   - Header row is **bold**
   - Auto-filter enabled (dropdown arrows on headers)
   - Columns are auto-sized

### 9.5 Individual Employee Export

1. Select employee: `EMP01 - Alice Engineer`
2. Format: `CSV`, click **Export**
3. **Expected**: CSV contains only EMP01's records

### 9.6 Department + Format Combo

1. Clear employee, select department: `Engineering`, format: `Excel`
2. Click **Export**
3. **Expected**: xlsx with only Engineering department employees

---

## Test 10: Team Attendance (MANAGER+)

1. Log in as `MGR01`
2. Go to **Team Attendance** (`/team`)
3. Set date range to today
4. **Expected**: Shows raw punch logs for Engineering department employees
5. Log in as `EMP01`
6. Go to **Dashboard** → **Team Attendance**
7. **Expected**: Access denied message

---

## Test 11: Attendance History (Self)

1. Log in as `EMP01`
2. Go to **Attendance History** (`/attendance`)
3. Set date range to today
4. **Expected**: Table shows all of EMP01's punch records from today with timestamps, work mode badges, and location data

---

## Test 12: Role-Based Access Control

| Page / Action | EMPLOYEE | MANAGER | HR | ADMIN |
|--------------|----------|---------|-----|-------|
| Punch | Yes | Yes | Yes | Yes |
| Own attendance history | Yes | Yes | Yes | Yes |
| Team attendance | No | Yes | Yes | Yes |
| Reports (daily) | No | Yes | Yes | Yes |
| Export (CSV/JSON/Excel) | No | No | Yes | Yes |
| Generate summaries | No | No | No | Yes |
| Admin panel | No | No | Yes | Yes |
| Create/edit employees | No | No | Yes | Yes |
| Update office location | No | No | Yes | Yes |
| Update grace period | No | No | Yes | Yes |
| System config (generic) | No | No | No | Yes |

**How to test**: Log in as each role and verify pages show content or "Access Denied".

---

## Test 13: i18n (Language Switching)

1. Log in as any user
2. Find the language switcher (top-right area)
3. Switch to **Chinese (繁體中文)**
4. **Expected**: All UI text switches to Chinese
5. Navigate to:
   - Punch page → "考勤打卡", button says "打卡"
   - Admin → Grace Period section shows "寬限時間"
   - Reports → Status badges show "準時", "遲到", "早退"
6. Punch when late:
   - **Expected**: Alert says "您已遲到，請在下方填寫原因。"
   - Reason label: "原因"
   - Submit button: "提交原因"
7. Switch back to English, verify all text reverts

---

## Test 14: GPS / Work Mode Detection

### 14.1 Office (within 2km)

1. If testing on a device physically near the configured office location:
   - Punch → **Expected**: Work Mode = `OFFICE`

2. If testing remotely with Chrome DevTools GPS override:
   - Open DevTools → **Sensors** tab → Override location
   - Set lat/lon near the office (e.g., `24.787, 120.998`)
   - Punch → **Expected**: Work Mode = `OFFICE`, distance < 2km

### 14.2 WFH (beyond 2km)

1. Set DevTools location to somewhere far (e.g., `25.033, 121.565` — Taipei)
2. Punch → **Expected**: Work Mode = `WFH`, distance > 2km

### 14.3 Low Accuracy Warning

1. This is harder to simulate manually. The backend flags `is_low_accuracy = true` when device accuracy > 500m
2. Via API:
```bash
curl -X POST http://localhost:8000/api/attendance/punch \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"latitude": 24.787, "longitude": 120.998, "accuracy": 600}'
# Expected: is_low_accuracy: true
```

---

## Test 15: Reason Submission — Edge Cases

### 15.1 Duplicate Reason Rejected

```bash
# Submit a reason for the same summary_id twice
curl -X POST http://localhost:8000/api/reasons \
  -H "Authorization: Bearer <EMP01_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"summary_id": 1, "reason": "Second attempt"}'
# Expected: 400 "Reason already submitted for this summary"
```

### 15.2 Wrong Employee

```bash
# EMP02 tries to submit reason for EMP01's summary
curl -X POST http://localhost:8000/api/reasons \
  -H "Authorization: Bearer <EMP02_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"summary_id": 1, "reason": "Not my summary"}'
# Expected: 400 "Summary does not belong to this employee"
```

### 15.3 Normal Status Rejected

```bash
# Try submitting reason for a NORMAL status summary
# Expected: 400 "Reason can only be submitted for LATE or EARLY_LEAVE status"
```

### 15.4 Manager Views Reasons

```bash
curl "http://localhost:8000/api/reasons?emp_id=EMP01" \
  -H "Authorization: Bearer <MGR01_TOKEN>"
# Expected: List of EMP01's submitted reasons
```

---

## Test 16: API Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```

---

## Quick Smoke Test Checklist

For a fast pass through the system, do these in order:

- [ ] Start services, seed data
- [ ] Set office location as HR01 (Test 2)
- [ ] Log in as EMP01 with password
- [ ] Try fingerprint login without registration — verify it fails with error (Test 1.3)
- [ ] Log in with password, register fingerprint on Dashboard (Test 1.4)
- [ ] Log out, fingerprint login — verify it works (Test 1.5)
- [ ] Punch on time (Test 4)
- [ ] Adjust EMP01 shift to make current time "late"
- [ ] Punch again — verify late alert + submit reason (Test 5)
- [ ] Log in as HR01, go to Reports, view daily report (Test 8)
- [ ] Export as Excel, verify file opens correctly (Test 9.4)
- [ ] Filter export by employee EMP01 (Test 9.5)
- [ ] Go to Admin, verify grace period section shows (Test 3)
- [ ] Switch language to Chinese, verify translations (Test 13)
- [ ] Reset EMP01 shift times

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "Office location not configured" on punch | No office location set | Complete Test 2 first |
| No tardiness alert despite being late | Grace period too large, or shift times don't match | Check grace period (Admin), check employee shift times |
| Export button does nothing | Not HR+ role | Log in as HR01 or ADMIN01 |
| "Reason already submitted" | Already submitted for this day | Each daily summary only allows one reason |
| Fingerprint login 400 error | Employee has not registered a fingerprint | Log in with password first, register fingerprint on Dashboard, then use fingerprint login |
| WebAuthn fails | HTTPS required in production; localhost works for dev | Use localhost, not IP address |
| 401 on API calls | Token expired (30 min) | Re-login to get a fresh token |
