# Human Test Manual — Phase 15 (Org Reporting Hierarchy & Subtree-Scoped Authority)

Covers the new **reporting tree** (`reports_to`), the **rank** label, the configurable **ranks** list, the **Manager Visibility Scoping** toggle, and the hardened **ADMIN-creation guard**.

> **The one-line behavior to verify:** when scoping is **ON**, a manager sees **only their own reports** (their reporting subtree) — never the whole company, and never a peer manager's team. When **OFF**, everything behaves exactly as before.

---

## Prerequisites

### Environment
1. PostgreSQL: `docker-compose up db -d`
2. Backend: `cd backend && alembic upgrade head && uvicorn app.main:app --reload --port 8000`
3. Frontend: `cd frontend && npm run dev`

### Verify the new columns exist (migration `b8c9d0e1f2a3`)
```bash
psql -U postgres -d attendance -c "\d employees" | grep -E "reports_to|rank"
```
Expected: a `reports_to` column (varchar, self-FK) and a `rank` column (varchar). If missing, run `alembic upgrade head` again.

### Seed users (`cd backend && python seed.py`)
| emp_id | password | role | department | name |
|--------|----------|------|------------|------|
| ADMIN01 | admin123 | ADMIN | IT | Admin User |
| HR01 | hr123456 | HR | HR | HR Manager |
| MGR01 | mgr12345 | MANAGER | Engineering | Engineering Manager |
| EMP01 | emp12345 | EMPLOYEE | Engineering | Alice Engineer |
| EMP02 | emp12345 | EMPLOYEE | Sales | Bob Sales |

> Password login works for these seed accounts. WebAuthn is **not** required for this manual.

### Concept recap (so the expected results make sense)
- **Capability** = the 4 roles (unchanged). AVP/VP/President are **not** roles.
- **Scope** = the `reports_to` tree. A manager's authority = their **subtree** (themselves + everyone reporting up to them, directly or indirectly). Department label is display-only.
- **Rank** = a label (MANAGER/AVP/VP/PRESIDENT). Display only — grants no power.
- **Toggle** (`Manager Visibility Scoping`) = master switch. **Default OFF** = legacy company-wide behavior.

---

## Scenario A — ADMIN-creation guard (Phase 15A)

1. Log in as **HR01**. Open **`/admin`** → **Employee Management** → **Add Employee**.
2. Open the **Role** dropdown.
   - ✅ **Expected:** options are **EMPLOYEE / MANAGER / HR** only. **No ADMIN option.**
3. Log out, log in as **ADMIN01**, open the same form.
   - ✅ **Expected:** the Role dropdown now **also** shows **ADMIN**.
4. (Optional, API) As HR, a crafted request to create an ADMIN is rejected:
   ```bash
   # TOKEN = HR01's JWT (from browser devtools → Application → localStorage, or the login response)
   curl -i -X POST http://localhost:8000/api/employees \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"emp_id":"X9","name":"x","department":"IT","role":"ADMIN","password":"pass12","shift_start_time":"09:00:00","shift_end_time":"18:00:00"}'
   ```
   - ✅ **Expected:** `403 Forbidden` (and `GET /api/employees/X9` → 404, not created).

---

## Scenario B — Manage the Ranks list (Phase 15C/15F)

1. As **HR01** (or ADMIN01) open **`/admin`** → **組織職級 / Org Ranks**.
   - ✅ **Expected:** defaults shown in order: **PRESIDENT, VP, AVP, MANAGER**.
2. Type `SVP` → **Add Rank**. Use the **▲ / ▼** arrows to move it under PRESIDENT. Click **Save**.
   - ✅ **Expected:** "Ranks saved". Reload the page → the new order persists.
3. Remove `SVP` again and Save (optional cleanup).

---

## Scenario C — Build the reporting tree (Phase 15B/15F)

Goal tree:
```
MGR01 (Engineering Manager)
  └─ EMP01 (Alice, Engineering)
EMP02 (Bob, Sales)  ← intentionally left with NO manager
```

1. As **HR01**, open **`/admin`** → **Employee Management**.
2. Edit **EMP01** (✏️). Set **直屬主管 / Reports to = Engineering Manager (MGR01)**. Optionally set **職級 / Rank = MANAGER** on MGR01. **Save**.
   - ✅ **Expected:** "Employee updated". Re-open EMP01's editor → Reports to still shows MGR01.
3. Edit **MGR01**. Optionally set **Rank = AVP**. Leave its **Reports to = None** (top of this branch). **Save**.
4. Leave **EMP02** with **Reports to = None**.

> The **Reports to** dropdown excludes the employee themselves and terminated staff. Deeper cycles are caught by the backend (next scenario).

---

## Scenario D — Cycle & self-reference prevention (Phase 15D)

1. As **HR01**, edit **MGR01** and set **Reports to = Alice Engineer (EMP01)** — i.e. point the boss at their own report. **Save**.
   - ✅ **Expected:** a red error message (HTTP **400**) — *"reports_to would create a cycle…"*. The change is **rejected**.
2. (Optional, API) Self-reference is also blocked:
   ```bash
   curl -i -X PUT http://localhost:8000/api/employees/MGR01 \
     -H "Authorization: Bearer $HR_TOKEN" -H "Content-Type: application/json" \
     -d '{"reports_to":"MGR01"}'
   ```
   - ✅ **Expected:** `400 Bad Request` — *"An employee cannot report to themselves"*.

---

## Scenario E — Baseline with scoping OFF (legacy behavior preserved)

1. As **HR01**, open **`/admin`** → **主管可視範圍 / Manager Visibility Scoping**. Confirm it is **OFF** (default).
2. Log in as **MGR01** (manager). Open the **Team** page (`/team`) and pick a date range covering today.
   - ✅ **Expected:** MGR01 sees attendance for employees per the **legacy** behavior (their department) — **EMP02 may appear if same department rules applied before; the point is: nothing has changed yet.**

> This step proves the feature is dark until you flip it on — no surprise regressions.

---

## Scenario F — Flip scoping ON: manager sees only their subtree (Phase 15E) ⭐ the core test

1. Log in as **HR01** → **`/admin`** → **Manager Visibility Scoping** → flip to **ON**.
   - ✅ **Expected:** label reads *"On — managers see only their team"*, "Scoping setting saved".
2. (Make sure some attendance exists — e.g. have **EMP01** and **EMP02** each clock in today via `/punch`, or use Monthly Override to set times.)
3. Log in as **MGR01**. Open the **Reports** view / **Team** page for today.
   - ✅ **Expected:** rows for **MGR01** and **EMP01** (the subtree). **EMP02 is NOT shown** — Bob is outside MGR01's branch.
4. Log in as **HR01** and open the same Reports view.
   - ✅ **Expected:** HR sees **everyone**, including **EMP02** (HR/ADMIN are always company-wide).

> **Key proof:** EMP01 (Engineering) appears for MGR01 because of the **reporting line**, while EMP02 (Sales) does not — authority follows the tree, not the department.

---

## Scenario G — Out-of-subtree actions blocked (override & reasons, Phase 15E)

With scoping **ON**, as **MGR01** (`$MGR_TOKEN`):
```bash
# In-subtree (EMP01) — allowed
curl -i -X POST http://localhost:8000/api/attendance/override \
  -H "Authorization: Bearer $MGR_TOKEN" -H "Content-Type: application/json" \
  -d '{"target_emp_id":"EMP01","latitude":25.0,"longitude":121.0,"accuracy":10,"work_mode":"OFFICE"}'
# Out-of-subtree (EMP02) — blocked
curl -i -X POST http://localhost:8000/api/attendance/override \
  -H "Authorization: Bearer $MGR_TOKEN" -H "Content-Type: application/json" \
  -d '{"target_emp_id":"EMP02","latitude":25.0,"longitude":121.0,"accuracy":10,"work_mode":"OFFICE"}'
```
- ✅ **Expected:** EMP01 → `200`; EMP02 → **`403 Forbidden`**.

Reasons lookup:
```bash
curl -i "http://localhost:8000/api/reasons?emp_id=EMP02" -H "Authorization: Bearer $MGR_TOKEN"   # 403
curl -i "http://localhost:8000/api/reasons?emp_id=EMP01" -H "Authorization: Bearer $MGR_TOKEN"   # 200
```

---

## Scenario H — Instant rollback

1. As **HR01** (or ADMIN01) → **`/admin`** → flip **Manager Visibility Scoping** back to **OFF**.
2. Re-check **MGR01**'s Team/Reports view.
   - ✅ **Expected:** managers immediately return to the legacy company-wide visibility. No data lost, no re-login needed.

---

## Expected-results matrix

| Scenario | Actor | Condition | Expected |
|----------|-------|-----------|----------|
| A | HR create form | — | No ADMIN option; API create ADMIN → 403 |
| A | ADMIN create form | — | ADMIN option present |
| B | HR | — | Ranks default PRESIDENT/VP/AVP/MANAGER; add/reorder/save persists |
| C | HR | — | reports_to + rank save and reload correctly |
| D | HR | set boss→own report / self | 400, rejected |
| E | MGR01 | toggle OFF | Legacy behavior, unchanged |
| F | MGR01 | toggle ON | Sees MGR01 + EMP01 only; **not** EMP02 |
| F | HR01 | toggle ON | Sees everyone (company-wide) |
| G | MGR01 | toggle ON | Override/reasons EMP01 → 200; EMP02 → 403 |
| H | HR01 | toggle OFF again | Managers back to company-wide instantly |

---

## Cleanup / reset
- Flip **Manager Visibility Scoping** **OFF** when done (default state).
- To wipe the tree: edit each employee and set **Reports to = None**, or re-run `python seed.py` against a fresh DB.

## Notes / known limitations
- Authority = visibility + override over your subtree. There is **no multi-level approval workflow** (overrides still take effect immediately).
- One boss per employee (single `reports_to`) — no matrix/dotted-line reporting.
- Rank is **display only**; it grants no permissions ("same powers, wider span").
- The team/reports **department picker** is not yet constrained for managers (cosmetic) — but results are already correctly subtree-filtered by the backend.
