# 2026-08 Monthly Patch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship 4 meeting-minute features: late-leave reason (延後下班原因) capture + submission gate, HRM export format + test-account exclusion, month-end override lock, and a schedule-confirmation banner.

**Architecture:** New nullable `late_leave_reason` column on `daily_attendance_summaries` follows the existing `overtime_hours` `_UNSET`-sentinel + round-trip pattern. Three new `system_config` keys (`late_reason_required_leave_types`, `export_excluded_emp_ids`, `monthly_override_lock`) follow the existing getter-with-default pattern. HRM export is a new `format=hrm` branch producing per-punch xlsx rows. Lock enforcement is a small service raising `PermissionError` for non-HR roles.

**Tech Stack:** FastAPI + SQLModel + Alembic + pytest/freezegun (backend); Next.js + React + vitest (frontend); openpyxl for xlsx.

**Spec:** `docs/superpowers/specs/2026-08-03-monthly-patch-design.md` — read it first; it is the authority on behavior.

## Global Constraints

- Branch: `feature/monthly-patch-202608`. TDD: write the failing test, see RED, implement, see GREEN, commit.
- `late_leave_reason` allowed values: exactly `"ASSIGNED_OVERTIME"` (A:主管指派加班·另外依程序填寫加班單) and `"PERSONAL"` (B:因個人原因留在辦公室), or NULL.
- Required-reason rule (used identically frontend + backend): day_kind ∈ {WORKDAY, MAKEUP_WORKDAY} AND last_clock_out strictly later than employee `shift_end_time` AND NOT (leave_type set and leave_type ∉ required-leave-types list) AND NOT single-punch (first == last) → reason required. 17:30 exactly = on time = not required.
- Config defaults: `late_reason_required_leave_types` → `["出差"]`; `export_excluded_emp_ids` → `["HR01", "ADMIN"]`; `monthly_override_lock` → unlocked.
- Excluded emp_ids apply to ALL export formats (csv/json/xlsx/hrm), even when `emp_id` query param explicitly names them. On-screen reports are NOT affected.
- Lock exempts HR and ADMIN. Lock blocks `PUT /api/attendance/override-bulk` and `POST /api/monthly-submissions` (403) for EMPLOYEE/MANAGER. Punching is never blocked by the lock.
- Backend commands run from `backend/` using the local venv (`.venv`); frontend from `frontend/`.
- All user-facing strings go through i18n (`frontend/src/messages/zh.json` + `en.json` — both files, every key).
- No `console.log`; immutable state updates only; follow file conventions already in each touched file.

---

### Task 1: `late_leave_reason` column — migration, model, repository & summary round-trip

**Files:**
- Create: `backend/alembic/versions/d0e1f2a3b4c5_add_late_leave_reason.py`
- Modify: `backend/app/models/daily_attendance_summary.py`
- Modify: `backend/app/repositories/summary_repository.py` (upsert_summary)
- Modify: `backend/app/services/reporting_service.py` (generate_daily_summary round-trip)
- Test: `backend/tests/integration/test_late_leave_reason_roundtrip.py`

**Interfaces:**
- Produces: `DailyAttendanceSummary.late_leave_reason: Optional[str]`; constant `LATE_LEAVE_REASONS = frozenset({"ASSIGNED_OVERTIME", "PERSONAL"})` in `app/models/daily_attendance_summary.py`; `upsert_summary(..., late_leave_reason: str | None | object = _UNSET)` — sentinel semantics identical to `overtime_hours` (later tasks rely on this exact kwarg).

- [ ] **Step 1: Write the failing test**

```python
"""late_leave_reason survives summary recompute (round-trip like overtime_hours)."""
import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role
from app.repositories import attendance_repository, summary_repository
from app.services import reporting_service
from app.utils.password import hash_password


async def _seed_employee(db_session: AsyncSession, emp_id: str = "E900") -> Employee:
    emp = Employee(
        emp_id=emp_id, name=f"User {emp_id}", department="Engineering",
        role=Role.EMPLOYEE, hashed_password=hash_password("pass1234"),
        shift_start_time=datetime.time(9, 0), shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    return emp


@pytest.mark.asyncio
async def test_late_leave_reason_survives_recompute(db_session: AsyncSession):
    await _seed_employee(db_session)
    date = datetime.date(2026, 7, 22)  # Wednesday
    for hh, mm in [(9, 0), (18, 40)]:
        await attendance_repository.create_log(db_session, AttendanceLog(
            emp_id="E900", timestamp=datetime.datetime.combine(date, datetime.time(hh, mm)),
            latitude=0.0, longitude=0.0, accuracy=0.0,
            ip_address="test", work_mode=WorkMode.OFFICE, is_overridden=False,
        ))

    await summary_repository.upsert_summary(
        db_session, emp_id="E900", date=date,
        first_clock_in=datetime.datetime.combine(date, datetime.time(9, 0)),
        last_clock_out=datetime.datetime.combine(date, datetime.time(18, 40)),
        status=AttendanceStatus.NORMAL, late_leave_reason="PERSONAL",
    )

    summary = await reporting_service.generate_daily_summary(db_session, "E900", date)
    assert summary is not None
    assert summary.late_leave_reason == "PERSONAL"


@pytest.mark.asyncio
async def test_upsert_sentinel_leaves_reason_alone(db_session: AsyncSession):
    await _seed_employee(db_session, "E901")
    date = datetime.date(2026, 7, 23)
    await summary_repository.upsert_summary(
        db_session, emp_id="E901", date=date, first_clock_in=None,
        last_clock_out=None, status=AttendanceStatus.ABSENT,
        late_leave_reason="ASSIGNED_OVERTIME",
    )
    # Second upsert without the kwarg must not clear it (sentinel default)
    row = await summary_repository.upsert_summary(
        db_session, emp_id="E901", date=date, first_clock_in=None,
        last_clock_out=None, status=AttendanceStatus.ABSENT,
    )
    assert row.late_leave_reason == "ASSIGNED_OVERTIME"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_late_leave_reason_roundtrip.py -v`
Expected: FAIL — `TypeError: upsert_summary() got an unexpected keyword argument 'late_leave_reason'`

- [ ] **Step 3: Implement**

Model (`daily_attendance_summary.py`) — add after `overtime_hours`, plus a module-level constant after the enum:

```python
LATE_LEAVE_REASONS: frozenset[str] = frozenset({"ASSIGNED_OVERTIME", "PERSONAL"})
```
```python
    late_leave_reason: Optional[str] = Field(default=None, max_length=30)
```

Migration `d0e1f2a3b4c5_add_late_leave_reason.py` (copy the header structure of `c9d0e1f2a3b4_add_webauthn_challenges.py`; `down_revision = "c9d0e1f2a3b4"`):

```python
def upgrade() -> None:
    op.add_column(
        "daily_attendance_summaries",
        sa.Column("late_leave_reason", sa.String(length=30), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("daily_attendance_summaries", "late_leave_reason")
```

`upsert_summary` — add kwarg `late_leave_reason: str | None | object = _UNSET` after `overtime_hours`; in the existing-row branch add:

```python
        if late_leave_reason is not _UNSET:
            existing.late_leave_reason = late_leave_reason  # type: ignore[assignment]
```

and in the new-row constructor:

```python
        late_leave_reason=None if late_leave_reason is _UNSET else late_leave_reason,  # type: ignore[arg-type]
```

`generate_daily_summary` — read + round-trip like overtime_hours:

```python
    existing_late_leave_reason = (
        existing_rows[0].late_leave_reason if existing_rows else None
    )
```
and pass `late_leave_reason=existing_late_leave_reason` in its `upsert_summary` call.

Run the migration against the dev DB: `cd backend && .venv\Scripts\python -m alembic upgrade head`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_late_leave_reason_roundtrip.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/d0e1f2a3b4c5_add_late_leave_reason.py backend/app/models/daily_attendance_summary.py backend/app/repositories/summary_repository.py backend/app/services/reporting_service.py backend/tests/integration/test_late_leave_reason_roundtrip.py
git commit -m "feat(db): add late_leave_reason column with round-trip semantics"
```

---

### Task 2: Punch accepts `late_leave_reason`

**Files:**
- Modify: `backend/app/schemas/attendance.py` (PunchGPSRequest)
- Modify: `backend/app/services/attendance_service.py` (punch)
- Modify: `backend/app/routers/attendance.py` (punch route)
- Test: `backend/tests/integration/test_punch_late_reason.py`

**Interfaces:**
- Consumes: Task 1's `upsert_summary(late_leave_reason=...)`, `LATE_LEAVE_REASONS`.
- Produces: `PunchGPSRequest.late_leave_reason: Optional[Literal["ASSIGNED_OVERTIME", "PERSONAL"]]`; `attendance_service.punch(..., late_leave_reason: str | None = None)`.

- [ ] **Step 1: Write the failing test**

Follow the auth/seed helper pattern from `tests/integration/test_bulk_override_clear.py` (`_make_token`, `_seed_employee`) and the office-location seeding used in `tests/integration/test_attendance_api.py::test_punch_success` (copy its system_config setup verbatim). Use `freeze_time` on a workday evening so the punch is past shift end and not a weekend:

```python
"""POST /api/attendance/punch stores late_leave_reason on the day's summary."""
import datetime

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# _make_token / _seed_employee / office-location seeding copied per note above


@pytest.mark.asyncio
@freeze_time("2026-07-22 18:31:00")  # Wednesday, after 18:00 shift end
async def test_punch_with_late_reason_stamps_summary(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, "E910")
    token = _make_token("E910", "EMPLOYEE")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post(
        "/api/attendance/punch",
        json={"latitude": 25.0330, "longitude": 121.5654, "accuracy": 10.0,
              "late_leave_reason": "PERSONAL"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    # Task 3 adds the key to GET /api/attendance/summaries; until then assert
    # via the repository so this task stays self-contained.
    from app.repositories import summary_repository
    rows = await summary_repository.find_by_employee(
        db_session, "E910",
        start_date=datetime.date(2026, 7, 22), end_date=datetime.date(2026, 7, 22),
    )
    assert rows and rows[0].late_leave_reason == "PERSONAL"


@pytest.mark.asyncio
@freeze_time("2026-07-22 18:31:00")
async def test_punch_rejects_unknown_reason_value(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, "E911")
    token = _make_token("E911", "EMPLOYEE")
    res = await client.post(
        "/api/attendance/punch",
        json={"latitude": 25.0330, "longitude": 121.5654, "accuracy": 10.0,
              "late_leave_reason": "SOMETHING_ELSE"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_punch_late_reason.py -v`
Expected: FAIL — 422 on the first test (unknown field is fine, but value not stored → assertion fails) or missing-kwarg TypeError.

- [ ] **Step 3: Implement**

`PunchGPSRequest`:

```python
from typing import Literal, Optional
# ...
class PunchGPSRequest(BaseModel):
    """Schema for a GPS-only punch request (no WebAuthn challenge)."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: float = Field(..., ge=0)
    late_leave_reason: Optional[Literal["ASSIGNED_OVERTIME", "PERSONAL"]] = None
```

`attendance_service.punch` — add param `late_leave_reason: str | None = None`; replace the tardiness-summary block (lines ~142-151) with:

```python
    # If tardy, auto-generate summary so employee can submit a reason.
    # Also regenerate when the punch carries a late-leave reason (超時下班),
    # so the reason can be stamped onto the fresh summary.
    summary_id = None
    summary = None
    if (
        tardiness_status in (AttendanceStatus.LATE, AttendanceStatus.EARLY_LEAVE)
        or late_leave_reason is not None
    ):
        summary = await reporting_service.generate_daily_summary(
            session, emp_id, saved_log.timestamp.date(), day_kind=day_kind
        )
    if late_leave_reason is not None and summary is not None:
        summary = await summary_repository.upsert_summary(
            session,
            emp_id=emp_id,
            date=saved_log.timestamp.date(),
            first_clock_in=summary.first_clock_in,
            last_clock_out=summary.last_clock_out,
            status=summary.status,
            leave_type=summary.leave_type,
            remark=summary.remark,
            late_leave_reason=late_leave_reason,
        )
    if tardiness_status in (AttendanceStatus.LATE, AttendanceStatus.EARLY_LEAVE):
        if summary is not None:
            summary_id = summary.id
```

(the stale `from app.services import reporting_service` local import inside the old block can be dropped — it is already imported at module top.)

Router `punch` route — pass through: `late_leave_reason=body.late_leave_reason,` in the `attendance_service.punch(...)` call.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_punch_late_reason.py tests/unit/test_attendance_service.py -v`
Expected: PASS (new tests + no regressions in existing punch tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/attendance.py backend/app/services/attendance_service.py backend/app/routers/attendance.py backend/tests/integration/test_punch_late_reason.py
git commit -m "feat(punch): accept and persist late_leave_reason"
```

---

### Task 3: Bulk override + summaries endpoint round-trip `late_leave_reason`

**Files:**
- Modify: `backend/app/schemas/bulk_override.py` (BulkOverrideEntry)
- Modify: `backend/app/services/attendance_service.py` (bulk_override_punches)
- Modify: `backend/app/routers/attendance.py` (get_my_summaries response)
- Test: `backend/tests/integration/test_bulk_override_late_reason.py`

**Interfaces:**
- Consumes: Task 1 sentinel kwarg.
- Produces: `BulkOverrideEntry.late_leave_reason` with #38 key-presence semantics; `GET /api/attendance/summaries` rows include `"late_leave_reason"`.

- [ ] **Step 1: Write the failing test**

Model on `tests/integration/test_bulk_override_clear.py` (reuse its `_make_token`, `_seed_employee`, `_get_summary_row` helpers verbatim):

```python
@pytest.mark.asyncio
async def test_bulk_override_sets_and_clears_late_reason(client, db_session):
    await _seed_employee(db_session, emp_id="E920")
    token = _make_token("E920", "EMPLOYEE")
    headers = {"Authorization": f"Bearer {token}"}

    # Set punches + reason (2026-05-14 is a Thursday workday)
    res = await client.put("/api/attendance/override-bulk", json={
        "year": 2026, "month": 5,
        "entries": [{"date": "2026-05-14", "first_clock_in": "09:00",
                     "last_clock_out": "19:00",
                     "late_leave_reason": "ASSIGNED_OVERTIME"}],
    }, headers=headers)
    assert res.status_code == 200, res.text
    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["late_leave_reason"] == "ASSIGNED_OVERTIME"

    # Omitted key → preserved
    res = await client.put("/api/attendance/override-bulk", json={
        "year": 2026, "month": 5,
        "entries": [{"date": "2026-05-14", "remark": "改備註"}],
    }, headers=headers)
    assert res.status_code == 200, res.text
    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["late_leave_reason"] == "ASSIGNED_OVERTIME"

    # Explicit null → cleared
    res = await client.put("/api/attendance/override-bulk", json={
        "year": 2026, "month": 5,
        "entries": [{"date": "2026-05-14", "late_leave_reason": None}],
    }, headers=headers)
    assert res.status_code == 200, res.text
    row = await _get_summary_row(client, token, "2026-05-14")
    assert row["late_leave_reason"] is None


@pytest.mark.asyncio
async def test_bulk_override_rejects_invalid_reason(client, db_session):
    await _seed_employee(db_session, emp_id="E921")
    token = _make_token("E921", "EMPLOYEE")
    res = await client.put("/api/attendance/override-bulk", json={
        "year": 2026, "month": 5,
        "entries": [{"date": "2026-05-14", "late_leave_reason": "NOPE"}],
    }, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_bulk_override_late_reason.py -v`
Expected: FAIL — `late_leave_reason` missing from the summaries response (KeyError) / value not persisted.

- [ ] **Step 3: Implement**

`BulkOverrideEntry` — add field + validator:

```python
    late_leave_reason: Optional[str] = Field(default=None, max_length=30)

    @field_validator("late_leave_reason")
    @classmethod
    def _validate_late_leave_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in LATE_LEAVE_REASONS:
            raise ValueError(
                "late_leave_reason must be ASSIGNED_OVERTIME or PERSONAL"
            )
        return v
```
(import `from app.models.daily_attendance_summary import LATE_LEAVE_REASONS`.)

`bulk_override_punches` — extend the key-presence block exactly like `overtime_hours`:
1. After `overtime_set = ...`: add `late_reason = entry.get("late_leave_reason")` and `late_reason_set = "late_leave_reason" in entry`.
2. Add `and not late_reason_set` to the skip-when-nothing-changes condition.
3. Gate the stamping block on `... or late_reason_set`; inside the existing-summary branch compute `final_late_reason = late_reason if late_reason_set else existing.late_leave_reason` and pass `late_leave_reason=final_late_reason` to `upsert_summary`; extend the `placeholder_status` ABSENT condition unchanged (reason alone never affects status).
4. In the no-existing-summary `elif`, add `or late_reason is not None` to the condition and pass `late_leave_reason=late_reason`.

`get_my_summaries` response dict — add:

```python
            "late_leave_reason": s.late_leave_reason,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_bulk_override_late_reason.py tests/integration/test_bulk_override_clear.py -v`
Expected: PASS, including the pre-existing clear-semantics suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/bulk_override.py backend/app/services/attendance_service.py backend/app/routers/attendance.py backend/tests/integration/test_bulk_override_late_reason.py
git commit -m "feat(override): late_leave_reason with explicit-null clear semantics"
```

---

### Task 4: Config getters + read-only leave-types endpoint

**Files:**
- Modify: `backend/app/repositories/system_config_repository.py`
- Modify: `backend/app/routers/system_config.py` (add GET /api/config/late-reason-leave-types)
- Test: `backend/tests/unit/test_new_config_getters.py`

**Interfaces:**
- Produces (all in `system_config_repository`):
  - `get_late_reason_required_leave_types(session) -> list[str]` (default `["出差"]`)
  - `get_export_excluded_emp_ids(session) -> list[str]` (default `["HR01", "ADMIN"]`)
  - `get_monthly_override_locked(session) -> bool` (default `False`)
  - `set_monthly_override_locked(session, locked: bool, updated_by: str | None) -> bool`
- Produces: `GET /api/config/late-reason-leave-types` (any authenticated user) → `{"leave_types": ["出差"]}`.

- [ ] **Step 1: Write the failing test**

```python
"""New system_config getters default correctly and honor stored values."""
import pytest

from app.repositories import system_config_repository as cfg


@pytest.mark.asyncio
async def test_late_reason_leave_types_default(db_session):
    assert await cfg.get_late_reason_required_leave_types(db_session) == ["出差"]


@pytest.mark.asyncio
async def test_late_reason_leave_types_stored(db_session):
    await cfg.set_config(db_session, "late_reason_required_leave_types",
                         {"leave_types": ["出差", "公出"]})
    assert await cfg.get_late_reason_required_leave_types(db_session) == ["出差", "公出"]


@pytest.mark.asyncio
async def test_export_excluded_default(db_session):
    assert await cfg.get_export_excluded_emp_ids(db_session) == ["HR01", "ADMIN"]


@pytest.mark.asyncio
async def test_override_lock_default_and_set(db_session):
    assert await cfg.get_monthly_override_locked(db_session) is False
    assert await cfg.set_monthly_override_locked(db_session, True, "HR01") is True
    assert await cfg.get_monthly_override_locked(db_session) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/unit/test_new_config_getters.py -v`
Expected: FAIL — AttributeError (functions missing)

- [ ] **Step 3: Implement**

Add to `system_config_repository.py`, following the `get_ranks` / `get_org_scoping_enabled` shapes exactly:

```python
_DEFAULT_LATE_REASON_LEAVE_TYPES: list[str] = ["出差"]


async def get_late_reason_required_leave_types(session: AsyncSession) -> list[str]:
    """Leave types (e.g. 出差) whose days still require a late-leave reason."""
    config = await get_by_key(session, "late_reason_required_leave_types")
    if config is None:
        return list(_DEFAULT_LATE_REASON_LEAVE_TYPES)
    value = config.value
    if isinstance(value, dict) and "leave_types" in value:
        return list(value["leave_types"])
    return list(_DEFAULT_LATE_REASON_LEAVE_TYPES)


_DEFAULT_EXPORT_EXCLUDED_EMP_IDS: list[str] = ["HR01", "ADMIN"]


async def get_export_excluded_emp_ids(session: AsyncSession) -> list[str]:
    """Seed/test accounts excluded from every report export format."""
    config = await get_by_key(session, "export_excluded_emp_ids")
    if config is None:
        return list(_DEFAULT_EXPORT_EXCLUDED_EMP_IDS)
    value = config.value
    if isinstance(value, dict) and "emp_ids" in value:
        return list(value["emp_ids"])
    return list(_DEFAULT_EXPORT_EXCLUDED_EMP_IDS)


async def get_monthly_override_locked(session: AsyncSession) -> bool:
    """Month-end settlement lock — blocks EMPLOYEE/MANAGER monthly edits."""
    config = await get_by_key(session, "monthly_override_lock")
    if config is None:
        return False
    value = config.value
    if isinstance(value, dict) and "locked" in value:
        return bool(value["locked"])
    return False


async def set_monthly_override_locked(
    session: AsyncSession, locked: bool, updated_by: str | None = None
) -> bool:
    await set_config(
        session, key="monthly_override_lock",
        value={"locked": bool(locked)}, updated_by=updated_by,
    )
    return bool(locked)
```

Router (`system_config.py`) — add alongside the existing endpoints (same auth dependency style as `get_workdays`, any authenticated user):

```python
@router.get("/late-reason-leave-types")
async def get_late_reason_leave_types(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Leave types whose days still require a late-leave reason (e.g. 出差)."""
    types = await system_config_repository.get_late_reason_required_leave_types(session)
    return {"leave_types": types}
```

(Check the file's existing imports — `get_current_user` may need importing; the router prefix is `/api/config`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/unit/test_new_config_getters.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/system_config_repository.py backend/app/routers/system_config.py backend/tests/unit/test_new_config_getters.py
git commit -m "feat(config): late-reason leave types, export exclusion, override lock keys"
```

---

### Task 5: Submission gate — missing late-leave reasons block `POST /api/monthly-submissions`

**Files:**
- Modify: `backend/app/services/monthly_submission_service.py`
- Modify: `backend/app/routers/monthly_submissions.py`
- Test: `backend/tests/integration/test_submission_late_reason_gate.py`

**Interfaces:**
- Consumes: Task 4 `get_late_reason_required_leave_types`; Task 1 column; `reporting_service._load_calendar_for_year`; `classify_date_kind` from `app.utils.taiwan_calendar`.
- Produces: `monthly_submission_service.find_missing_late_reason_dates(session, emp_id, year, month) -> list[datetime.date]`; router returns 400 with `detail={"code": "late_reason_missing", "message": ..., "dates": [...]}`.

- [ ] **Step 1: Write the failing test**

Reuse `_make_token` / `_seed_employee` helpers (shift 09:00–18:00). Seed summaries directly via `summary_repository.upsert_summary`:

```python
@pytest.mark.asyncio
async def test_submit_blocked_when_reason_missing(client, db_session):
    await _seed_employee(db_session, "E930")
    token = _make_token("E930", "EMPLOYEE")
    d = datetime.date(2026, 7, 22)  # Wednesday workday
    await summary_repository.upsert_summary(
        db_session, emp_id="E930", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(9, 0)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(19, 0)),
        status=AttendanceStatus.NORMAL,
    )
    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E930", "year": 2026, "month": 7},
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "late_reason_missing"
    assert "2026-07-22" in detail["dates"]


@pytest.mark.asyncio
async def test_submit_ok_when_reason_filled_or_exempt(client, db_session):
    await _seed_employee(db_session, "E931")
    token = _make_token("E931", "EMPLOYEE")
    mk = lambda day, **kw: summary_repository.upsert_summary(  # noqa: E731
        db_session, emp_id="E931", date=datetime.date(2026, 7, day), **kw)
    dt = lambda day, h, m: datetime.datetime.combine(  # noqa: E731
        datetime.date(2026, 7, day), datetime.time(h, m))

    # late clock-out but reason filled → OK
    await mk(22, first_clock_in=dt(22, 9, 0), last_clock_out=dt(22, 19, 0),
             status=AttendanceStatus.NORMAL, late_leave_reason="PERSONAL")
    # on-time 18:00 exactly → exempt
    await mk(23, first_clock_in=dt(23, 9, 0), last_clock_out=dt(23, 18, 0),
             status=AttendanceStatus.NORMAL)
    # leave day (特休 not in required list) with late clock-out → exempt
    await mk(24, first_clock_in=dt(24, 9, 0), last_clock_out=dt(24, 19, 0),
             status=AttendanceStatus.LEAVE, leave_type="特休")
    # single punch (first == last) → exempt (no clock-out yet)
    await mk(27, first_clock_in=dt(27, 19, 0), last_clock_out=dt(27, 19, 0),
             status=AttendanceStatus.LATE)

    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E931", "year": 2026, "month": 7},
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_submit_blocked_on_business_trip_late_clockout(client, db_session):
    await _seed_employee(db_session, "E932")
    token = _make_token("E932", "EMPLOYEE")
    d = datetime.date(2026, 7, 22)
    await summary_repository.upsert_summary(
        db_session, emp_id="E932", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(9, 0)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(19, 0)),
        status=AttendanceStatus.LEAVE, leave_type="出差",
    )
    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E932", "year": 2026, "month": 7},
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "late_reason_missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_submission_late_reason_gate.py -v`
Expected: FAIL — submissions currently succeed (200)

- [ ] **Step 3: Implement**

`monthly_submission_service.py`:

```python
import calendar as _calendar
import datetime

from app.repositories import employee_repository, summary_repository, system_config_repository
from app.services.reporting_service import _load_calendar_for_year
from app.utils.taiwan_calendar import DayKind, classify_date_kind

_REQUIRED_DAY_KINDS = frozenset({DayKind.WORKDAY, DayKind.MAKEUP_WORKDAY})


async def find_missing_late_reason_dates(
    session: AsyncSession, emp_id: str, year: int, month: int
) -> list[datetime.date]:
    """Workdays whose last clock-out runs past shift end without a reason.

    Mirrors the frontend rule exactly: workday-kind days only, strict
    ``time > shift_end``, single-punch days exempt (no clock-out yet — #16),
    leave days exempt unless the leave type is in the configured
    still-requires list (e.g. 出差).
    """
    employee = await employee_repository.find_by_id(session, emp_id)
    if employee is None:
        return []
    required_leave_types = set(
        await system_config_repository.get_late_reason_required_leave_types(session)
    )
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, _calendar.monthrange(year, month)[1])
    summaries = await summary_repository.find_by_employee(
        session, emp_id, start_date=first, end_date=last
    )
    calendar_data = await _load_calendar_for_year(session, year)

    missing: list[datetime.date] = []
    for s in summaries:
        if classify_date_kind(calendar_data, s.date) not in _REQUIRED_DAY_KINDS:
            continue
        if s.leave_type and s.leave_type not in required_leave_types:
            continue
        if s.first_clock_in is None or s.last_clock_out is None:
            continue
        if s.first_clock_in == s.last_clock_out:
            continue
        if s.last_clock_out.time() <= employee.shift_end_time:
            continue
        if s.late_leave_reason:
            continue
        missing.append(s.date)
    return sorted(missing)
```

Router `submit_month` — insert before the `submit_month` service call:

```python
    missing = await monthly_submission_service.find_missing_late_reason_dates(
        session, emp_id=body.emp_id, year=body.year, month=body.month
    )
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "late_reason_missing",
                "message": "延後下班原因未填寫完成，無法送單",
                "dates": [d.isoformat() for d in missing],
            },
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_submission_late_reason_gate.py -v`
Expected: PASS (3 tests). Also run any existing monthly-submission tests: `.venv\Scripts\python -m pytest tests/ -k "submission" -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/monthly_submission_service.py backend/app/routers/monthly_submissions.py backend/tests/integration/test_submission_late_reason_gate.py
git commit -m "feat(submission): server-side gate for missing late-leave reasons"
```

---

### Task 6: Override-lock API + enforcement

**Files:**
- Create: `backend/app/services/override_lock_service.py`
- Create: `backend/app/routers/override_lock.py`
- Create: `backend/app/schemas/override_lock.py`
- Modify: `backend/app/main.py` (register router — mirror how the leave_types router is registered)
- Modify: `backend/app/routers/attendance.py` (bulk_override route)
- Modify: `backend/app/routers/monthly_submissions.py` (submit_month route)
- Test: `backend/tests/integration/test_override_lock.py`

**Interfaces:**
- Consumes: Task 4 `get_monthly_override_locked` / `set_monthly_override_locked`.
- Produces: `GET /api/admin/override-lock` (any auth) → `{"locked": bool}`; `PUT /api/admin/override-lock` (HR+) body `{"locked": bool}`; `override_lock_service.ensure_not_locked(session, role)` raising `PermissionError`.

- [ ] **Step 1: Write the failing test**

```python
"""Month-end override lock — HR/ADMIN exempt, EMPLOYEE/MANAGER blocked."""
# _make_token / _seed_employee as in test_bulk_override_clear.py

ENTRY = {"date": "2026-05-14", "first_clock_in": "09:00", "last_clock_out": "18:00"}


async def _set_lock(client, locked: bool):
    hr_token = _make_token("HRX", "HR")
    res = await client.put("/api/admin/override-lock", json={"locked": locked},
                           headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 200, res.text
    return res


@pytest.mark.asyncio
async def test_lock_blocks_employee_but_not_hr(client, db_session):
    await _seed_employee(db_session, "E940")
    await _seed_employee(db_session, "HRX", role=Role.HR)
    await _set_lock(client, True)

    # Employee blocked from bulk override
    emp_token = _make_token("E940", "EMPLOYEE")
    res = await client.put("/api/attendance/override-bulk",
        json={"year": 2026, "month": 5, "entries": [ENTRY]},
        headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 403

    # Employee blocked from submission
    res = await client.post("/api/monthly-submissions",
        json={"emp_id": "E940", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 403

    # HR can still bulk-override the employee
    hr_token = _make_token("HRX", "HR")
    res = await client.put("/api/attendance/override-bulk",
        json={"year": 2026, "month": 5, "emp_id": "E940", "entries": [ENTRY]},
        headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 200, res.text

    # Release restores employee access
    await _set_lock(client, False)
    res = await client.put("/api/attendance/override-bulk",
        json={"year": 2026, "month": 5, "entries": [ENTRY]},
        headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_lock_read_any_auth_write_hr_only(client, db_session):
    await _seed_employee(db_session, "E941")
    emp_token = _make_token("E941", "EMPLOYEE")
    res = await client.get("/api/admin/override-lock",
                           headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 200
    assert res.json() == {"locked": False}

    res = await client.put("/api/admin/override-lock", json={"locked": True},
                           headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_override_lock.py -v`
Expected: FAIL — 404 on /api/admin/override-lock

- [ ] **Step 3: Implement**

`app/schemas/override_lock.py`:

```python
"""Schemas for the month-end override lock."""
from pydantic import BaseModel


class OverrideLockResponse(BaseModel):
    locked: bool


class OverrideLockUpdateRequest(BaseModel):
    locked: bool
```

`app/services/override_lock_service.py`:

```python
"""Month-end override lock — blocks EMPLOYEE/MANAGER monthly edits while HR settles."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Role
from app.repositories import system_config_repository

_EXEMPT_ROLES = frozenset({Role.HR, Role.ADMIN})


async def ensure_not_locked(session: AsyncSession, role: Role) -> None:
    """Raise PermissionError when the lock is on and *role* is not exempt."""
    if role in _EXEMPT_ROLES:
        return
    if await system_config_repository.get_monthly_override_locked(session):
        raise PermissionError("月結鎖定中，月度打卡修改與送單暫停開放，請聯絡人資")
```

`app/routers/override_lock.py` (mirror `leave_types.py` — GET any auth, PUT HR+):

```python
"""Override-lock config router.

GET — any authenticated user (pages need it to render read-only state).
PUT — HR or above; flips the month-end settlement lock.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_role
from app.models.employee import Role
from app.repositories import system_config_repository
from app.schemas.override_lock import OverrideLockResponse, OverrideLockUpdateRequest

router = APIRouter(prefix="/api/admin/override-lock", tags=["admin-override-lock"])


@router.get("", response_model=OverrideLockResponse)
async def get_override_lock(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OverrideLockResponse:
    locked = await system_config_repository.get_monthly_override_locked(session)
    return OverrideLockResponse(locked=locked)


@router.put("", response_model=OverrideLockResponse)
async def put_override_lock(
    body: OverrideLockUpdateRequest,
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> OverrideLockResponse:
    locked = await system_config_repository.set_monthly_override_locked(
        session, body.locked, updated_by=user["sub"]
    )
    return OverrideLockResponse(locked=locked)
```

Register in `app/main.py` next to the other routers (same include_router pattern as leave_types).

Enforcement — `attendance.py::bulk_override`, first lines of the try-block (PermissionError already maps to 403 there):

```python
        await override_lock_service.ensure_not_locked(session, Role(user["role"]))
```
(move it INSIDE the existing `try:` so the except clause catches it; import `from app.services import override_lock_service`.)

`monthly_submissions.py::submit_month`, after the `_can_act_on` check:

```python
    try:
        await override_lock_service.ensure_not_locked(session, Role(user.get("role", "EMPLOYEE")))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_override_lock.py tests/integration/test_bulk_override_clear.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/override_lock_service.py backend/app/routers/override_lock.py backend/app/schemas/override_lock.py backend/app/main.py backend/app/routers/attendance.py backend/app/routers/monthly_submissions.py backend/tests/integration/test_override_lock.py
git commit -m "feat(lock): month-end override lock API + enforcement (HR/ADMIN exempt)"
```

---

### Task 7: Export exclusion list (all formats)

**Files:**
- Modify: `backend/app/services/reporting_service.py` (export_attendance)
- Test: `backend/tests/integration/test_export_exclusion.py`

**Interfaces:**
- Consumes: Task 4 `get_export_excluded_emp_ids`.
- Produces: `export_attendance` never emits rows (real or filler) for excluded emp_ids in any format.

- [ ] **Step 1: Write the failing test**

```python
"""Excluded seed accounts (HR01/ADMIN by default) never appear in exports."""
# _seed_employee helper as before; seed summaries via summary_repository

@pytest.mark.asyncio
async def test_excluded_accounts_absent_from_csv_and_json(db_session):
    await _seed_employee(db_session, "HR01", role=Role.HR)
    await _seed_employee(db_session, "E950")
    d = datetime.date(2026, 7, 22)
    for eid in ("HR01", "E950"):
        await summary_repository.upsert_summary(
            db_session, emp_id=eid, date=d,
            first_clock_in=datetime.datetime.combine(d, datetime.time(9, 0)),
            last_clock_out=datetime.datetime.combine(d, datetime.time(18, 0)),
            status=AttendanceStatus.NORMAL)

    csv_out = await reporting_service.export_attendance(
        db_session, start_date=d, end_date=d, format="csv",
        submission_filter="all")
    assert "E950" in csv_out
    assert "HR01" not in csv_out

    json_out = await reporting_service.export_attendance(
        db_session, start_date=d, end_date=d, format="json",
        submission_filter="all")
    assert "HR01" not in json_out


@pytest.mark.asyncio
async def test_exclusion_wins_even_with_explicit_emp_id(db_session):
    await _seed_employee(db_session, "ADMIN", role=Role.ADMIN)
    d = datetime.date(2026, 7, 22)
    await summary_repository.upsert_summary(
        db_session, emp_id="ADMIN", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(9, 0)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(18, 0)),
        status=AttendanceStatus.NORMAL)
    out = await reporting_service.export_attendance(
        db_session, start_date=d, end_date=d, format="csv",
        emp_id="ADMIN", submission_filter="all")
    assert "ADMIN" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_export_exclusion.py -v`
Expected: FAIL — HR01/ADMIN present in output

- [ ] **Step 3: Implement**

In `export_attendance`, immediately after the `get_daily_report(...)` call:

```python
    # Seed/test accounts (default HR01/ADMIN) never reach any export format —
    # even an explicit emp_id filter naming them (meeting decision 2026-08-03).
    excluded = set(
        await system_config_repository.get_export_excluded_emp_ids(session)
    )
    all_summaries = [s for s in all_summaries if s.emp_id not in excluded]
```

and after `emp_map` is fully built (after the slipped-through loop) filter it so filler rows skip them too:

```python
    emp_map = {eid: e for eid, e in emp_map.items() if eid not in excluded}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_export_exclusion.py tests/integration/test_export_chinese.py -v`
Expected: PASS, no regressions in existing export tests. If any existing export test seeds an employee literally named `HR01`/`ADMIN` and now fails, rename that fixture employee (the exclusion is the desired behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reporting_service.py backend/tests/integration/test_export_exclusion.py
git commit -m "feat(export): exclude configured seed/test accounts from all formats"
```

---

### Task 8: HRM export format

**Files:**
- Modify: `backend/app/services/reporting_service.py` (new `export_attendance_hrm` + constants)
- Modify: `backend/app/routers/reports.py` (accept `format=hrm`)
- Test: `backend/tests/integration/test_export_hrm.py`

**Interfaces:**
- Consumes: `get_daily_report`, Task 7 exclusion, openpyxl.
- Produces: `export_attendance_hrm(session, start_date, end_date, department=None, emp_id=None, include_terminated=False, submission_filter="submitted") -> bytes`; `GET /api/reports/export?format=hrm` → xlsx download `hrm_export_{start}_{end}.xlsx`.

- [ ] **Step 1: Write the failing test**

```python
"""HRM export: per-punch rows, 序號, unpadded dates, fixed APP打卡 label."""
import io

from openpyxl import load_workbook

# seeding helpers as before

@pytest.mark.asyncio
async def test_hrm_export_two_rows_per_full_day(db_session):
    await _seed_employee(db_session, "E960")
    d = datetime.date(2026, 7, 24)
    await summary_repository.upsert_summary(
        db_session, emp_id="E960", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(8, 30)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(17, 30)),
        status=AttendanceStatus.NORMAL)

    content = await reporting_service.export_attendance_hrm(
        db_session, start_date=d, end_date=d, submission_filter="all")
    ws = load_workbook(io.BytesIO(content)).active

    header = [c.value for c in ws[1]]
    assert header == ["序號", "工號", "姓名", "考勤機ID", "刷卡日期", "刷卡時間",
                      "補刷卡假勤類型原因"]
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
    assert rows == [
        [1, "E960", "User E960", None, "2026/7/24", "08:30", "APP打卡"],
        [2, "E960", "User E960", None, "2026/7/24", "17:30", "APP打卡"],
    ]


@pytest.mark.asyncio
async def test_hrm_export_single_punch_one_row_and_absent_none(db_session):
    await _seed_employee(db_session, "E961")
    d = datetime.date(2026, 7, 24)
    # single punch: first == last → one row only
    await summary_repository.upsert_summary(
        db_session, emp_id="E961", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(8, 30)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(8, 30)),
        status=AttendanceStatus.NORMAL)
    content = await reporting_service.export_attendance_hrm(
        db_session, start_date=d, end_date=d, submission_filter="all")
    ws = load_workbook(io.BytesIO(content)).active
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
    assert len(rows) == 1 and rows[0][5] == "08:30"


@pytest.mark.asyncio
async def test_hrm_export_excludes_seed_accounts(db_session):
    await _seed_employee(db_session, "HR01", role=Role.HR)
    d = datetime.date(2026, 7, 24)
    await summary_repository.upsert_summary(
        db_session, emp_id="HR01", date=d,
        first_clock_in=datetime.datetime.combine(d, datetime.time(8, 30)),
        last_clock_out=datetime.datetime.combine(d, datetime.time(17, 30)),
        status=AttendanceStatus.NORMAL)
    content = await reporting_service.export_attendance_hrm(
        db_session, start_date=d, end_date=d, submission_filter="all")
    ws = load_workbook(io.BytesIO(content)).active
    assert list(ws.iter_rows(min_row=2)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_export_hrm.py -v`
Expected: FAIL — AttributeError: export_attendance_hrm missing

- [ ] **Step 3: Implement**

Constants near `CHINESE_HEADERS`:

```python
HRM_HEADERS = ["序號", "工號", "姓名", "考勤機ID", "刷卡日期", "刷卡時間", "補刷卡假勤類型原因"]
HRM_PUNCH_LABEL = "APP打卡"  # fixed for every row regardless of punch source


def _format_hrm_date(d: datetime.date) -> str:
    """HRM system wants unpadded YYYY/M/D (e.g. 2026/7/24)."""
    return f"{d.year}/{d.month}/{d.day}"
```

New function (after `export_attendance`):

```python
async def export_attendance_hrm(
    session: AsyncSession,
    start_date: datetime.date,
    end_date: datetime.date,
    department: str | None = None,
    emp_id: str | None = None,
    include_terminated: bool = False,
    submission_filter: Literal["submitted", "unsubmitted", "all"] = "submitted",
) -> bytes:
    """HRM-system import format: one xlsx row per punch (first-in, last-out).

    Days without punches (ABSENT / pure-leave / holiday) emit nothing; a
    single-punch day (first == last, #16: clock-in only) emits one row. The
    考勤機ID column stays blank and the source label is always APP打卡 —
    per the 2026-08-03 meeting decision, punch origin is not distinguished.
    """
    summaries = await get_daily_report(
        session,
        start_date=start_date,
        end_date=end_date,
        department=department,
        emp_id=emp_id,
        include_terminated=include_terminated,
        submission_filter=submission_filter,
    )
    excluded = set(
        await system_config_repository.get_export_excluded_emp_ids(session)
    )
    summaries = [s for s in summaries if s.emp_id not in excluded]

    name_map: dict[str, str] = {}
    for eid in {s.emp_id for s in summaries}:
        emp = await employee_repository.find_by_id(session, eid)
        name_map[eid] = emp.name if emp else ""

    punch_rows: list[tuple[str, str, datetime.date, datetime.time]] = []
    for s in summaries:
        if s.first_clock_in is None:
            continue
        punch_rows.append(
            (s.emp_id, name_map[s.emp_id], s.date, s.first_clock_in.time())
        )
        if s.last_clock_out is not None and s.last_clock_out != s.first_clock_in:
            punch_rows.append(
                (s.emp_id, name_map[s.emp_id], s.date, s.last_clock_out.time())
            )
    punch_rows.sort(key=lambda r: (r[2], r[0], r[3]))

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "HRM Import"
    bold = Font(bold=True)
    for col_idx, header in enumerate(HRM_HEADERS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = bold
    for idx, (eid, name, d, t) in enumerate(punch_rows, 1):
        ws.append([idx, eid, name, None, _format_hrm_date(d),
                   t.strftime("%H:%M"), HRM_PUNCH_LABEL])

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
```

Router `export_report` — before the existing `export_attendance` call:

```python
    if format == "hrm":
        content = await reporting_service.export_attendance_hrm(
            session,
            start_date=start_date,
            end_date=end_date,
            department=department,
            emp_id=emp_id,
            include_terminated=include_terminated,
            submission_filter=effective_filter,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=hrm_export_{start_date}_{end_date}.xlsx",
            },
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_export_hrm.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reporting_service.py backend/app/routers/reports.py backend/tests/integration/test_export_hrm.py
git commit -m "feat(export): HRM-system xlsx format (per-punch rows)"
```

---

### Task 9: `/api/auth/me` returns shift times

**Files:**
- Modify: `backend/app/routers/auth.py` (me endpoint)
- Test: `backend/tests/integration/test_auth_me_profile.py`

**Interfaces:**
- Produces: `GET /api/auth/me` → `{"emp_id", "role", "name", "shift_start_time": "HH:MM", "shift_end_time": "HH:MM"}` (shift keys omitted only if the employee row is missing). Frontend Tasks 10-12 consume `shift_end_time`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_me_includes_shift_times(client, db_session):
    await _seed_employee(db_session, "E970")  # shift 09:00-18:00
    token = _make_token("E970", "EMPLOYEE")
    res = await client.get("/api/auth/me",
                           headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["emp_id"] == "E970"
    assert body["shift_start_time"] == "09:00"
    assert body["shift_end_time"] == "18:00"
    assert body["name"] == "User E970"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_auth_me_profile.py -v`
Expected: FAIL — KeyError shift_start_time

- [ ] **Step 3: Implement**

```python
@router.get("/me")
async def me(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Return the current user's identity plus shift times (for the punch
    page's late-leave dialog and the monthly-override required-reason rule)."""
    result = {"emp_id": user["sub"], "role": user["role"]}
    employee = await employee_repository.find_by_id(session, user["sub"])
    if employee is not None:
        result["name"] = employee.name
        result["shift_start_time"] = employee.shift_start_time.strftime("%H:%M")
        result["shift_end_time"] = employee.shift_end_time.strftime("%H:%M")
    return result
```

(add `employee_repository` / `get_db` imports if not present in auth.py.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/integration/test_auth_me_profile.py tests/ -k "auth" -v`
Expected: PASS, no auth regressions. If a pre-existing test asserts the exact old `/me` shape (`== {"emp_id": ..., "role": ...}`), update that assertion to the new superset shape — the change is intentional.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/integration/test_auth_me_profile.py
git commit -m "feat(auth): /me returns name and shift times"
```

---

### Task 10: Punch page — late-leave reason confirmation modal

**Files:**
- Create: `frontend/src/components/LateLeaveReasonModal.tsx`
- Create: `frontend/src/hooks/useMyProfile.ts`
- Modify: `frontend/src/app/punch/page.tsx`
- Modify: `frontend/src/types/index.ts` (LateLeaveReason, MyProfile, PunchRequest)
- Modify: `frontend/src/messages/zh.json` + `frontend/src/messages/en.json`
- Test: `frontend/src/components/__tests__/LateLeaveReasonModal.test.tsx`, extend `frontend/src/app/punch/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: Task 9 `/api/auth/me` (`shift_end_time`), Task 2 punch payload field.
- Produces: `LateLeaveReason = "ASSIGNED_OVERTIME" | "PERSONAL"`; `useMyProfile(): { profile: MyProfile | null }`; `LateLeaveReasonModal` props `{ open, shiftEnd, value, onChange, onConfirm }`.

- [ ] **Step 1: Write the failing tests**

`LateLeaveReasonModal.test.tsx` (follow the render/i18n-mock pattern of existing component tests, e.g. the OvertimePunchModal or WarningModal tests):

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LateLeaveReasonModal } from "@/components/LateLeaveReasonModal";

describe("LateLeaveReasonModal", () => {
  it("renders both options with PERSONAL preselected and no cancel button", () => {
    render(
      <LateLeaveReasonModal open shiftEnd="17:30" value="PERSONAL"
        onChange={vi.fn()} onConfirm={vi.fn()} />,
    );
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(screen.getByRole("radio", { checked: true })).toHaveAttribute(
      "value", "PERSONAL",
    );
    // exactly one button: confirm — no cancel path
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByText(/17:30/)).toBeInTheDocument();
  });

  it("confirm fires onConfirm; selecting A fires onChange", () => {
    const onConfirm = vi.fn();
    const onChange = vi.fn();
    render(
      <LateLeaveReasonModal open shiftEnd="17:30" value="PERSONAL"
        onChange={onChange} onConfirm={onConfirm} />,
    );
    fireEvent.click(screen.getAllByRole("radio")[0]);
    expect(onChange).toHaveBeenCalledWith("ASSIGNED_OVERTIME");
    fireEvent.click(screen.getByRole("button"));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
```

Punch page test additions (in the existing `page.test.tsx`, reusing its mock setup — mock `/api/auth/me` to return `shift_end_time: "17:30"` and freeze time with `vi.setSystemTime`):

```tsx
it("opens the late-reason modal when punching after shift end and sends the reason", async () => {
  vi.setSystemTime(new Date("2026-07-22T18:31:00"));  // Wed after 17:30
  // ... render, click punch button
  // modal appears instead of immediate submit:
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  // confirm → punch POST body includes late_leave_reason: "PERSONAL"
  fireEvent.click(screen.getByRole("button", { name: /確認|Confirm/ }));
  await waitFor(() => {
    expect(mockedApiPost).toHaveBeenCalledWith(
      "/api/attendance/punch",
      expect.objectContaining({ late_leave_reason: "PERSONAL" }),
    );
  });
});

it("does not open the modal before shift end", async () => {
  vi.setSystemTime(new Date("2026-07-22T17:30:00"));  // exactly on time
  // ... click punch; expect no dialog and a direct POST without the field
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/__tests__/LateLeaveReasonModal.test.tsx src/app/punch`
Expected: FAIL — component missing

- [ ] **Step 3: Implement**

Types (`types/index.ts`):

```ts
export type LateLeaveReason = "ASSIGNED_OVERTIME" | "PERSONAL";

export interface MyProfile {
  readonly emp_id: string;
  readonly role: Role;
  readonly name?: string;
  readonly shift_start_time?: string;
  readonly shift_end_time?: string;
}
```
and add `readonly late_leave_reason?: LateLeaveReason;` to the frontend `PunchRequest`.

`hooks/useMyProfile.ts`:

```ts
"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api";
import type { MyProfile } from "@/types";

/** Fetches /api/auth/me once — shift times drive the late-leave dialog. */
export function useMyProfile(enabled: boolean): { profile: MyProfile | null } {
  const [profile, setProfile] = useState<MyProfile | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    apiClient
      .get<MyProfile>("/api/auth/me")
      .then((data) => {
        if (!cancelled) setProfile(data);
      })
      .catch(() => {
        // silent — without shift times the dialog simply never triggers
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { profile };
}
```

`LateLeaveReasonModal.tsx` — copy the modal shell of `OvertimePunchModal.tsx` (fixed overlay, role="dialog", aria labels, memo export) with these differences: no overlay-click close, no Escape close (confirm-only per spec), body is a radio list:

```tsx
"use client";

import { memo } from "react";
import { AlertTriangle } from "lucide-react";

import { useTranslation } from "@/lib/i18n";
import type { LateLeaveReason } from "@/types";

export interface LateLeaveReasonModalProps {
  readonly open: boolean;
  readonly shiftEnd: string;
  readonly value: LateLeaveReason;
  readonly onChange: (value: LateLeaveReason) => void;
  readonly onConfirm: () => void;
}

const TITLE_ID = "late-leave-reason-modal-title";

const OPTIONS: readonly { value: LateLeaveReason; labelKey: string }[] = [
  { value: "ASSIGNED_OVERTIME", labelKey: "punch.lateReasonAssignedOvertime" },
  { value: "PERSONAL", labelKey: "punch.lateReasonPersonal" },
];

function LateLeaveReasonModalImpl({
  open, shiftEnd, value, onChange, onConfirm,
}: LateLeaveReasonModalProps) {
  const { t } = useTranslation();
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={TITLE_ID}
        className="w-full max-w-lg rounded-lg bg-white text-left shadow-xl"
      >
        <div className="flex items-start gap-3 border-b border-gray-200 p-5">
          <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-500" aria-hidden />
          <h2 id={TITLE_ID} className="text-base font-semibold text-gray-900">
            {t("punch.lateReasonTitle").replace("{time}", shiftEnd)}
          </h2>
        </div>
        <div className="space-y-3 p-5">
          {OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-gray-200 p-3 text-sm text-gray-800 has-[:checked]:border-[#4ec6c1] has-[:checked]:bg-[#e8faf9]"
            >
              <input
                type="radio"
                name="late-leave-reason"
                value={opt.value}
                checked={value === opt.value}
                onChange={() => onChange(opt.value)}
                className="mt-0.5 h-4 w-4 text-[#4ec6c1] focus:ring-[#4ec6c1]"
              />
              <span>{t(opt.labelKey)}</span>
            </label>
          ))}
        </div>
        <div className="flex justify-end border-t border-gray-200 p-4">
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-[#4ec6c1] px-6 py-2 text-sm font-medium text-white hover:bg-[#45b5b0] focus:outline-none focus:ring-2 focus:ring-[#4ec6c1]"
          >
            {t("punch.lateReasonConfirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

export const LateLeaveReasonModal = memo(LateLeaveReasonModalImpl);
```

Punch page wiring:

```tsx
const { profile } = useMyProfile(isAuthenticated);
const [reasonModalOpen, setReasonModalOpen] = useState(false);
const [lateReason, setLateReason] = useState<LateLeaveReason>("PERSONAL");
const lateReasonRef = useRef<LateLeaveReason | null>(null);

const isWorkdayKind =
  todayKind === "WORKDAY" || todayKind === "MAKEUP_WORKDAY";

function nowHHMM(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

const needsLateReason = (): boolean =>
  isWorkdayKind &&
  !!profile?.shift_end_time &&
  nowHHMM() > profile.shift_end_time;
```

**Calendar-probe change (required):** the page's existing day_kind effect early-returns unless the local guess is `REST_DAY` (Saturday). That was fine when day_kind only gated the button, but the dialog must also stay silent on weekday national holidays (no scheduled shift — spec 1.2). Remove the `if (deriveDayKindFromDate(today) !== "REST_DAY") return;` line so the calendar is probed every load; keep the local-guess seed and the silent catch. Cost: one extra GET per page load.

- `submitPunch` gains an optional 4th param and includes `late_leave_reason` in the body only when non-null.
- Wrap the button handler: `handlePunchClick` checks `needsLateReason()`; if true and `lateReasonRef.current === null`, it opens the modal (`setLateReason("PERSONAL"); setReasonModalOpen(true)`) and returns without punching. The modal's `onConfirm` sets `lateReasonRef.current = lateReason`, closes the modal, and calls the original `handlePunch`.
- Both submit paths (direct + geolocation effect) read `lateReasonRef.current` when building the payload and reset it to `null` in their `finally` blocks (alongside `submitLockRef`).
- Render `<LateLeaveReasonModal open={reasonModalOpen} shiftEnd={profile?.shift_end_time ?? ""} value={lateReason} onChange={setLateReason} onConfirm={handleReasonConfirm} />` at the page root.

i18n keys (zh / en):

```json
"punch": {
  "lateReasonTitle": "您填寫的時間已超過您的班別 {time} 應下班時間，請勾選以下原因：",
  "lateReasonAssignedOvertime": "A:主管指派加班·另外依程序填寫加班單",
  "lateReasonPersonal": "B:因個人原因留在辦公室",
  "lateReasonConfirm": "確認"
}
```
```json
"punch": {
  "lateReasonTitle": "Your punch time is past your scheduled end time of {time}. Please select a reason:",
  "lateReasonAssignedOvertime": "A: Supervisor-assigned overtime (file an overtime request separately)",
  "lateReasonPersonal": "B: Stayed in the office for personal reasons",
  "lateReasonConfirm": "Confirm"
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/__tests__/LateLeaveReasonModal.test.tsx src/app/punch`
Expected: PASS (new + existing punch tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LateLeaveReasonModal.tsx frontend/src/hooks/useMyProfile.ts frontend/src/app/punch/page.tsx frontend/src/types/index.ts frontend/src/messages/zh.json frontend/src/messages/en.json frontend/src/components/__tests__/LateLeaveReasonModal.test.tsx frontend/src/app/punch/__tests__/page.test.tsx
git commit -m "feat(punch): confirm-only late-leave reason dialog (default B)"
```

---

### Task 11: Monthly-override — 延後下班原因 column

**Files:**
- Modify: `frontend/src/app/dashboard/monthly-override/page.tsx`
- Modify: `frontend/src/types/index.ts` (DailyAttendanceSummary + BulkOverrideEntry gain `late_leave_reason`)
- Modify: `frontend/src/messages/zh.json` + `en.json`
- Test: extend `frontend/src/app/dashboard/monthly-override/__tests__/page.test.tsx` (or the page's existing test file — locate with `npx vitest list` / glob `monthly-override/**/*.test.tsx`)

**Interfaces:**
- Consumes: Task 3 (`GET /api/attendance/summaries` returns `late_leave_reason`; PUT accepts it), Task 10 types.
- Produces: `DayRow.lateLeaveReason: string | null`; new table column between 下班(24h) and 假別 headed `monthlyOverride.lateLeaveReason`; select `data-testid="late-reason-select"` with options `"" | ASSIGNED_OVERTIME | PERSONAL`.

- [ ] **Step 1: Write the failing test**

Add to the existing monthly-override page test file (reuse its API-mock scaffolding — it already mocks `/api/attendance/summaries` and `/api/config/workdays`):

```tsx
it("renders the late-leave reason column, prefills it, and saves changes", async () => {
  // mock summaries response for one workday with late_leave_reason: "PERSONAL"
  // ... render page, wait for table
  const selects = await screen.findAllByTestId("late-reason-select");
  expect(selects.length).toBeGreaterThan(0);
  // prefilled from API
  expect(
    (screen.getAllByTestId("late-reason-select")[targetIdx] as HTMLSelectElement).value,
  ).toBe("PERSONAL");
  // change to A and save → PUT body carries late_leave_reason
  fireEvent.change(selects[targetIdx], { target: { value: "ASSIGNED_OVERTIME" } });
  fireEvent.click(screen.getByRole("button", { name: /儲存|Save/ }));
  await waitFor(() => {
    expect(mockedApiPut).toHaveBeenCalledWith(
      "/api/attendance/override-bulk",
      expect.objectContaining({
        entries: expect.arrayContaining([
          expect.objectContaining({ late_leave_reason: "ASSIGNED_OVERTIME" }),
        ]),
      }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/dashboard/monthly-override`
Expected: FAIL — no late-reason-select test ids

- [ ] **Step 3: Implement**

Types: add `readonly late_leave_reason?: string | null;` to `DailyAttendanceSummary` and `BulkOverrideEntry` in `types/index.ts`.

Page changes:
1. `DayRow` gains `readonly lateLeaveReason: string | null;` — built from `summary?.late_leave_reason ?? null`.
2. New handler:

```tsx
const handleLateReasonChange = useCallback((date: string, value: string) => {
  const next = value === "" ? null : value;
  setRows((prev) =>
    prev.map((row) =>
      row.date === date ? { ...row, lateLeaveReason: next } : row,
    ),
  );
}, []);
```
3. Changed-row detection adds `row.lateLeaveReason !== orig.lateLeaveReason`; payload entries add `late_leave_reason: row.lateLeaveReason,`.
4. Table: new `<th>` right after the 下班(24h) header (`{t("monthlyOverride.lateLeaveReason")}`); new `<td>` after the clock-out cell:

```tsx
<td className="px-4 py-3">
  {row.isEditable ? (
    <select
      data-testid="late-reason-select"
      value={row.lateLeaveReason ?? ""}
      onChange={(e) => handleLateReasonChange(row.date, e.target.value)}
      className="max-w-[11rem] rounded-lg border border-gray-300 px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-[#4ec6c1] focus:ring-1 focus:ring-[#4ec6c1] focus:outline-none"
    >
      <option value="">—</option>
      <option value="ASSIGNED_OVERTIME">
        {t("monthlyOverride.lateReasonAssignedOvertimeShort")}
      </option>
      <option value="PERSONAL">
        {t("monthlyOverride.lateReasonPersonalShort")}
      </option>
    </select>
  ) : (
    <span className="text-gray-400">-</span>
  )}
</td>
```
(min-w-[720px] on the table may need bumping to min-w-[840px] so the new column fits.)

i18n:

```json
"monthlyOverride": {
  "lateLeaveReason": "延後下班原因",
  "lateReasonAssignedOvertimeShort": "A:主管指派加班",
  "lateReasonPersonalShort": "B:因個人原因留在辦公室"
}
```
(en: `"Late-leave reason"`, `"A: Assigned overtime"`, `"B: Personal reasons"`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/dashboard/monthly-override`
Expected: PASS (note: one pre-existing `waitFor` flake exists in this suite — rerun once before treating a timeout as a new failure)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/dashboard/monthly-override/page.tsx frontend/src/types/index.ts frontend/src/messages/zh.json frontend/src/messages/en.json frontend/src/app/dashboard/monthly-override/__tests__
git commit -m "feat(monthly-override): editable late-leave reason column"
```

---

### Task 12: Monthly-override — required-reason cues + submission hard-block

**Files:**
- Create: `frontend/src/components/LateReasonMissingModal.tsx`
- Modify: `frontend/src/app/dashboard/monthly-override/page.tsx`
- Modify: `frontend/src/messages/zh.json` + `en.json`
- Test: extend the monthly-override page test file; `frontend/src/components/__tests__/LateReasonMissingModal.test.tsx`

**Interfaces:**
- Consumes: Task 4 `GET /api/config/late-reason-leave-types`, Task 9 `/api/auth/me`, Task 10 `useMyProfile`, Task 11 column.
- Produces: `rowNeedsLateLeaveReason(row, shiftEnd, requiredLeaveTypes)` helper; `LateReasonMissingModal` props `{ open, dates, onClose }` (clone of OvertimePunchModal with its own i18n keys).

- [ ] **Step 1: Write the failing tests**

Modal test: copy the OvertimePunchModal test structure — renders title with count, lists dates, single close button.

Page test:

```tsx
it("hard-blocks 本月送單 when a required late-leave reason is missing", async () => {
  // summaries mock: workday with clock-out 19:00 (shift end 18:00 via /api/auth/me mock),
  // late_leave_reason: null
  // ... render, click submit-month button
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(screen.getByText(/2026-07-22/)).toBeInTheDocument();
  // the submission API must NOT have been called
  expect(mockedSubmit).not.toHaveBeenCalled();
});

it("allows 本月送單 when reasons are filled or day is exempt", async () => {
  // same setup but late_leave_reason: "PERSONAL" → submit proceeds
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/app/dashboard/monthly-override src/components/__tests__/LateReasonMissingModal.test.tsx`
Expected: FAIL

- [ ] **Step 3: Implement**

`LateReasonMissingModal.tsx`: copy `OvertimePunchModal.tsx` wholesale, rename component/props/test-ids, and swap the i18n keys to `monthlyOverride.lateReasonMissingTitle` / `monthlyOverride.lateReasonMissingBody` (close button reuses `monthlyOverride.backToEdit`).

Page:
1. Fetch prerequisites: `const { profile } = useMyProfile(true);` and a mount-effect loading required leave types:

```tsx
const [requiredLeaveTypes, setRequiredLeaveTypes] = useState<readonly string[]>(["出差"]);
// effect: apiClient.get<{ leave_types: string[] }>("/api/config/late-reason-leave-types")
//   .then((d) => setRequiredLeaveTypes(d.leave_types)).catch(() => {/* keep default */});
```
2. Target shift end — HR viewing another employee uses that employee's shift; self uses profile:

```tsx
const targetShiftEnd: string | null = (() => {
  if (isHrPlus && selectedEmpId) {
    const emp = employees.find((e) => e.emp_id === selectedEmpId);
    return emp?.shift_end_time ?? null;
  }
  return profile?.shift_end_time ?? null;
})();
```
3. The shared rule (module-level, next to `rowNeedsPunchForOvertime`):

```tsx
/**
 * Late-leave reason is required on workday-kind days whose clock-out runs
 * strictly past shift end. Leave days are exempt unless the leave type is in
 * the configured still-requires list (e.g. 出差). Mirrors the backend gate in
 * monthly_submission_service.find_missing_late_reason_dates.
 */
function rowNeedsLateLeaveReason(
  row: DayRow,
  shiftEnd: string | null,
  requiredLeaveTypes: readonly string[],
): boolean {
  if (!row.isEditable || !shiftEnd) return false;
  if (row.day_kind !== "WORKDAY" && row.day_kind !== "MAKEUP_WORKDAY") return false;
  if (row.leaveType && !requiredLeaveTypes.includes(row.leaveType)) return false;
  const out = row.clockOut.trim();
  if (out === "" || out.length < 5) return false;
  if (out <= shiftEnd) return false;
  return !row.lateLeaveReason;
}
```
4. Derived list + modal state:

```tsx
const lateReasonMissingDates: readonly string[] = rows
  .filter((row) => rowNeedsLateLeaveReason(row, targetShiftEnd, requiredLeaveTypes))
  .map((row) => row.date);
const [lateReasonModalOpen, setLateReasonModalOpen] = useState(false);
```
5. `handleSubmitMonth` — insert the hard-block before the abnormal-days check:

```tsx
if (lateReasonMissingDates.length > 0) {
  setLateReasonModalOpen(true);
  return;
}
```
6. Row cues: in the row render, when `rowNeedsLateLeaveReason(...)` is true add `border-red-400 bg-red-50` to the late-reason select's className and an `<AlertTriangle>` icon beside it (copy the `rowNeedsPunchForOvertime` cue block); extend `getRowClass` usage by prepending the same `bg-red-50 border-l-4 border-l-red-500` class via a wrapper: `const rowClass = needsReason ? "bg-red-50 border-l-4 border-l-red-500" : getRowClass(row);` computed inline in the map.
7. Render `<LateReasonMissingModal open={lateReasonModalOpen} dates={lateReasonMissingDates} onClose={() => setLateReasonModalOpen(false)} />`.
8. `performSubmit` catch — surface the backend 400 detail message when present (the ApiError already carries object-shaped detail per CLAUDE.md #32e).

i18n:

```json
"monthlyOverride": {
  "lateReasonMissingTitle": "有 {count} 天需勾選延後下班原因",
  "lateReasonMissingBody": "以下日期的下班時間已超過班別應下班時間，請先勾選「延後下班原因」再送單："
}
```
(en: `"{count} day(s) need a late-leave reason"`, `"These dates have a clock-out past the scheduled end time. Select a late-leave reason before submitting:"`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/app/dashboard/monthly-override src/components/__tests__/LateReasonMissingModal.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LateReasonMissingModal.tsx frontend/src/app/dashboard/monthly-override/page.tsx frontend/src/messages/zh.json frontend/src/messages/en.json frontend/src/app/dashboard/monthly-override/__tests__ frontend/src/components/__tests__/LateReasonMissingModal.test.tsx
git commit -m "feat(monthly-override): required late-reason cues + submission hard-block"
```

---

### Task 13: Reports page — HRM export button

**Files:**
- Modify: `frontend/src/app/reports/page.tsx` (export section)
- Modify: `frontend/src/messages/zh.json` + `en.json`
- Test: extend the reports page test file (`frontend/src/app/reports/__tests__/`)

**Interfaces:**
- Consumes: Task 8 `format=hrm` endpoint.
- Produces: button labeled `reports.hrmExport` (「HRM系統使用」) that downloads `hrm_export_{start}_{end}.xlsx`.

- [ ] **Step 1: Write the failing test**

```tsx
it("HRM export button fetches format=hrm and downloads xlsx", async () => {
  // render export section, mock global fetch to return an xlsx blob
  fireEvent.click(await screen.findByRole("button", { name: /HRM系統使用|HRM/ }));
  await waitFor(() => {
    const url = (global.fetch as Mock).mock.calls.at(-1)![0] as string;
    expect(url).toContain("/api/reports/export");
    expect(url).toContain("format=hrm");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/reports`
Expected: FAIL — button not found

- [ ] **Step 3: Implement**

Refactor `handleExport(e)` into `doExport(exportFormat: string)` (the form's onSubmit calls `doExport(format)`; all existing logic keeps working — the binary branch becomes `if (exportFormat === "csv" || exportFormat === "xlsx" || exportFormat === "hrm")`). Filename for hrm: `a.download = \`hrm_export_${startDate}_${endDate}.xlsx\`;` (skip `buildExportFilename` for this fixed-name format). Add the button next to the existing submit button:

```tsx
<button
  type="button"
  disabled={isExporting}
  onClick={() => doExport("hrm")}
  className="rounded-lg border border-[#4ec6c1] bg-white px-4 py-1.5 text-sm font-medium text-[#4ec6c1] hover:bg-[#e8faf9] disabled:cursor-not-allowed disabled:opacity-50"
>
  {t("reports.hrmExport")}
</button>
```

i18n: `"hrmExport": "HRM系統使用"` (en: `"For HRM system"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/reports`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/reports/page.tsx frontend/src/messages/zh.json frontend/src/messages/en.json frontend/src/app/reports/__tests__
git commit -m "feat(reports): HRM-system export button"
```

---

### Task 14: Lock frontend — admin section + monthly-override read-only mode

**Files:**
- Create: `frontend/src/components/admin/OverrideLockSection.tsx`
- Create: `frontend/src/lib/api/override-lock.ts`
- Modify: `frontend/src/app/admin/page.tsx` (render section next to `<OrgScopingSection />`)
- Modify: `frontend/src/app/dashboard/monthly-override/page.tsx`
- Modify: `frontend/src/messages/zh.json` + `en.json`
- Test: `frontend/src/components/admin/__tests__/OverrideLockSection.test.tsx`; extend monthly-override page tests

**Interfaces:**
- Consumes: Task 6 GET/PUT `/api/admin/override-lock`.
- Produces: `overrideLockApi.get(): Promise<{locked: boolean}>` / `overrideLockApi.set(locked): Promise<{locked: boolean}>`; monthly-override page renders `data-testid="override-lock-banner"` and disables all editing for non-HR when locked.

- [ ] **Step 1: Write the failing tests**

`OverrideLockSection.test.tsx` (mirror the OrgScopingSection test structure if one exists; otherwise):

```tsx
it("shows current state and toggles lock via PUT", async () => {
  mockedGet.mockResolvedValue({ locked: false });
  mockedSet.mockResolvedValue({ locked: true });
  render(<OverrideLockSection />);
  const btn = await screen.findByTestId("override-lock-toggle");
  fireEvent.click(btn);
  await waitFor(() => expect(mockedSet).toHaveBeenCalledWith(true));
});
```

Monthly-override page test:

```tsx
it("locks the page for employees when override lock is on", async () => {
  // mock GET /api/admin/override-lock → { locked: true }, role EMPLOYEE
  expect(await screen.findByTestId("override-lock-banner")).toBeInTheDocument();
  expect(screen.queryAllByTestId("clock-in-input")).toHaveLength(0); // all rows read-only
  expect(screen.getByRole("button", { name: /送單|Submit/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /儲存|Save/ })).toBeDisabled();
});

it("does not lock the page for HR when override lock is on", async () => {
  // same mock, role HR → inputs still rendered, no banner
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/admin src/app/dashboard/monthly-override`
Expected: FAIL

- [ ] **Step 3: Implement**

`lib/api/override-lock.ts` (mirror `lib/api/org-hierarchy.ts`'s orgScopingApi shape):

```ts
import { apiClient } from "@/lib/api";

export interface OverrideLockState {
  readonly locked: boolean;
}

export const overrideLockApi = {
  get: () => apiClient.get<OverrideLockState>("/api/admin/override-lock"),
  set: (locked: boolean) =>
    apiClient.put<OverrideLockState>("/api/admin/override-lock", { locked }),
};
```

`OverrideLockSection.tsx`: copy `OrgScopingSection.tsx` structure (state, load-on-mount, toggle handler, message banner) with: `Lock` icon from lucide-react, `data-testid="override-lock-toggle"`, i18n keys `admin.overrideLock*`, and the action button text switching 鎖定 ↔ 釋放:

```tsx
<span className="text-sm font-medium text-gray-800">
  {locked ? t("admin.overrideLockOn") : t("admin.overrideLockOff")}
</span>
```
(keep the switch pattern; the state label makes 鎖定中/未鎖定 explicit.)

Admin page: render `<OverrideLockSection />` immediately after `<OrgScopingSection />`.

Monthly-override page:
1. Load lock state once:

```tsx
const [overrideLocked, setOverrideLocked] = useState(false);
// mount effect: overrideLockApi.get().then((d) => setOverrideLocked(Boolean(d?.locked))).catch(() => {})
const pageLocked = overrideLocked && !isHrPlus;
```
2. In `fetchData`'s row builder, force `isEditable = isEditable && !pageLocked` (add `pageLocked` to the `useCallback` deps so rows rebuild when it resolves).
3. Banner above the table (after the timeFormatHint block):

```tsx
{!isLoading && pageLocked && (
  <div
    role="alert"
    data-testid="override-lock-banner"
    className="mb-3 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm font-medium text-red-800"
  >
    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
    <span>{t("monthlyOverride.lockedBanner")}</span>
  </div>
)}
```
4. Disable both action buttons: add `|| pageLocked` to the Save and Submit buttons' `disabled` props.

i18n:

```json
"admin": {
  "overrideLock": "月結鎖定",
  "overrideLockHint": "鎖定後，一般員工與主管無法使用月度打卡修改與本月送單；HR/ADMIN 不受影響。",
  "overrideLockOn": "鎖定中 — 點擊釋放",
  "overrideLockOff": "未鎖定 — 點擊鎖定",
  "overrideLockSaved": "月結鎖定狀態已更新",
  "overrideLockSaveError": "更新失敗，請稍後再試"
},
"monthlyOverride": {
  "lockedBanner": "人資月結作業中，月度打卡修改暫停開放，如有問題請聯絡人資。"
}
```
(en equivalents: "Month-end lock", "While locked, employees and managers cannot edit or submit monthly attendance; HR/ADMIN are unaffected.", "Locked — click to release", "Unlocked — click to lock", "Lock state updated", "Update failed, please retry", "Month-end settlement in progress — monthly override is temporarily closed. Contact HR with questions.")

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/admin src/app/dashboard/monthly-override src/app/admin`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/admin/OverrideLockSection.tsx frontend/src/lib/api/override-lock.ts frontend/src/app/admin/page.tsx frontend/src/app/dashboard/monthly-override/page.tsx frontend/src/messages/zh.json frontend/src/messages/en.json frontend/src/components/admin/__tests__ frontend/src/app/dashboard/monthly-override/__tests__
git commit -m "feat(lock): admin lock/release section + monthly-override read-only mode"
```

---

### Task 15: Schedule-confirmation banner + full verification + docs

**Files:**
- Modify: `frontend/src/app/dashboard/monthly-override/page.tsx`
- Modify: `frontend/src/messages/zh.json` + `en.json`
- Modify: `CLAUDE.md` (new design-decision entry #39)
- Test: extend monthly-override page tests

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
it("renders the schedule confirmation notice", async () => {
  // render page (any role)
  expect(await screen.findByTestId("schedule-notice")).toHaveTextContent(
    /本月份排班表已依個人意願/,
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/dashboard/monthly-override`
Expected: FAIL

- [ ] **Step 3: Implement**

Banner directly below the timeFormatHint note block (visible to all roles):

```tsx
{!isLoading && (
  <div
    role="note"
    data-testid="schedule-notice"
    className="mb-3 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-100 px-3 py-2 text-sm font-medium text-amber-900"
  >
    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
    <span>{t("monthlyOverride.scheduleNotice")}</span>
  </div>
)}
```

i18n zh: `"scheduleNotice": "備註：本月份排班表已依個人意願與公司工作需求排定，若對班表有疑慮或錯誤者，請與單位主管和人資進行修改確認，若逾期未提出，則視為同意本月排班，謝謝。"`
en: `"scheduleNotice": "Note: This month's schedule was arranged per personal preference and company needs. If you have concerns or find errors, please confirm changes with your supervisor and HR. Without timely feedback the schedule is deemed accepted. Thank you."`

- [ ] **Step 4: Full verification (both stacks — do not skip)**

```bash
cd backend && .venv\Scripts\python -m pytest --cov=app --cov-report=term-missing
cd frontend && npx vitest run && npm run build
```
Expected: all backend tests green (457 pre-existing + new), coverage ≥ 80%; all frontend tests green (149 pre-existing + new, modulo the known monthly-override `waitFor` flake — rerun once); production build succeeds.

- [ ] **Step 5: Update CLAUDE.md**

Add design-decision entry **#39** summarizing (concise, following the existing entry style): late_leave_reason column + values + required rule + exemptions (leave days exempt, `late_reason_required_leave_types` default 出差 still required) + punch dialog (confirm-only, default PERSONAL, workday-kind + past-shift-end trigger) + dual submission gate (frontend hard-block + backend 400 `late_reason_missing` structured detail); HRM export (`format=hrm`, per-punch rows, fixed APP打卡, unpadded dates) + `export_excluded_emp_ids` (all formats, wins over explicit emp_id); `monthly_override_lock` (global, HR/ADMIN exempt, blocks override-bulk + submissions); `/api/auth/me` now returns shift times; monthly-override schedule notice banner. Update the test-count line.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/dashboard/monthly-override/page.tsx frontend/src/messages/zh.json frontend/src/messages/en.json frontend/src/app/dashboard/monthly-override/__tests__ CLAUDE.md
git commit -m "feat(monthly-override): schedule confirmation notice + docs"
```

---

## Post-plan (not tasks — session-level)

- Code review (`feature-dev:code-reviewer`, opus) per dev-flow Step 5; security review (`security-review` skill) — this patch touches auth (`/me`), new endpoints, and user input.
- Push to BOTH remotes (origin + bitbucket) only on Kenny's instruction.
- Migration must run in prod during deploy: `docker compose -f docker-compose.prod.yml exec backend alembic upgrade head`.
