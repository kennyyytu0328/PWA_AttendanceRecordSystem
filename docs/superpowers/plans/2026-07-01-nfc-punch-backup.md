# NFC Door-Tap Gap-Fill Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an API-key-authenticated backend endpoint that ingests a SOYAL 701 `YYYYMM.txt` door-tap export and per-side gap-fills missing phone punches, plus a PowerShell agent that pushes the file daily.

**Architecture:** The office door PC (behind NAT/DHCP) pushes the CP950 file to `POST /api/nfc/import` over HTTPS with a shared API key. The backend decodes CP950, parses rows, and for each `(emp_id, date)` fills only the missing clock-in and/or clock-out from door taps — a real phone punch always wins. Idempotent because a filled side is never re-filled. Daily summaries are regenerated with the Taiwan-calendar `day_kind`.

**Tech Stack:** Python 3.13, FastAPI, SQLModel/SQLAlchemy async, pytest + pytest-asyncio (sqlite in-memory for tests), PowerShell (door agent).

Design spec: `docs/superpowers/specs/2026-07-01-nfc-punch-backup-design.md` (zh-TW: `…-design.zh-TW.md`).

## Global Constraints

- Branch: `feature/nfc-punch-backup` (already checked out; keep `main` untouched).
- Python: async everywhere (`async def` / `await`); type hints on all signatures.
- Repository pattern — no direct DB queries in services/routers; reuse existing repo functions.
- Immutable patterns — frozen dataclasses for service result types.
- NFC-inserted logs use marker `ip_address="nfc"`, `work_mode=WorkMode.OFFICE`, `latitude=longitude=accuracy=0.0`, `is_overridden=False`.
- File encoding is **CP950** (`raw.decode("cp950", errors="replace")`).
- **No DB migration** — the source marker reuses `ip_address`.
- Join key is field 3 = native `emp_id`. Field 4 (`door_no`) is NOT direction; in/out is inferred by time (earliest = clock-in, latest = clock-out).
- Record all taps including weekends/Sundays; `generate_daily_summary(day_kind=…)` scores non-working days NORMAL.
- Security: API key via header `X-NFC-API-Key`, compared with `hmac.compare_digest` to env var `NFC_IMPORT_API_KEY`; never hardcoded. Machine-to-machine (no JWT).
- TDD (RED→GREEN→commit); target 80%+ coverage. Functions < 50 lines, files < 800 lines.
- No `print`/`console.log` in production code. Conventional-commit messages; **no** `Co-Authored-By` trailer (attribution disabled globally).
- Backend commands run from `backend/` via the native venv: `pytest …` (see project rules — local backend is native `.venv`, not Docker).

---

## File Structure

- **Create** `backend/app/services/nfc_import_service.py` — CP950 decode, row parse, per-side gap-fill orchestration, calendar-aware summary regen. (Tasks 2 + 3)
- **Create** `backend/app/schemas/nfc.py` — `NfcImportResponse` Pydantic model. (Task 4)
- **Create** `backend/app/routers/nfc.py` — `POST /api/nfc/import` + `require_nfc_api_key` dependency. (Task 5)
- **Modify** `backend/app/config.py` — add `nfc_import_api_key` setting. (Task 1)
- **Modify** `backend/app/main.py` — register the nfc router. (Task 5)
- **Modify** `backend/.env.example` and `backend/.env.production.example` — document `NFC_IMPORT_API_KEY`. (Task 1)
- **Create** `backend/tests/unit/test_nfc_import_service.py` — decode/parse/gap-fill unit tests. (Tasks 2 + 3)
- **Create** `backend/tests/integration/test_nfc_import_api.py` — endpoint + auth tests. (Task 5)
- **Create** `tools/nfc-agent/push-nfc.ps1` and `tools/nfc-agent/README.md` — door-side push agent. (Task 6)

---

## Task 1: Config setting + env templates

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`, `backend/.env.production.example`

**Interfaces:**
- Produces: `settings.nfc_import_api_key: str` (default `""` = feature disabled).

- [ ] **Step 1: Add the setting**

In `backend/app/config.py`, inside `class Settings`, after the `root_path` field:

```python
    # NFC door-tap import (SOYAL 701 push agent). Machine-to-machine shared
    # secret checked on POST /api/nfc/import. Empty ("") disables the endpoint.
    nfc_import_api_key: str = ""
```

- [ ] **Step 2: Document it in the env templates**

Append to `backend/.env.example` (create the line if the file exists; if it does not, create the file with just this line):

```
# NFC door-tap import shared secret (leave blank to disable /api/nfc/import)
NFC_IMPORT_API_KEY=change-me-in-production
```

Append the same two lines to `backend/.env.production.example`.

- [ ] **Step 3: Verify it imports**

Run: `python -c "from app.config import settings; print(repr(settings.nfc_import_api_key))"`
Expected: prints `''` (or whatever `.env` holds). No exception.

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/.env.production.example
git commit -m "feat(nfc): add NFC_IMPORT_API_KEY setting and env templates"
```

---

## Task 2: CP950 decode + row parser (pure functions)

**Files:**
- Create: `backend/app/services/nfc_import_service.py`
- Test: `backend/tests/unit/test_nfc_import_service.py`

**Interfaces:**
- Produces:
  - `NfcTap` frozen dataclass: `emp_id: str`, `timestamp: datetime.datetime`, `door_no: str`, `card_serial: str`, `name: str`.
  - `decode_file(raw: bytes) -> str`
  - `parse_rows(text: str) -> tuple[list[NfcTap], list[str]]` — returns (taps, malformed-raw-lines).
  - Module constants `CARD_ENCODING = "cp950"`, `NFC_IP_MARKER = "nfc"`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_nfc_import_service.py`:

```python
"""Unit tests for the NFC door-tap import service."""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role
from app.repositories import attendance_repository, summary_repository


def _make_employee(
    emp_id: str = "F1000118",
    role: Role = Role.EMPLOYEE,
    terminated_at: datetime.datetime | None = None,
) -> Employee:
    return Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=role,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
        terminated_at=terminated_at,
    )


def _cp950(rows: list[str]) -> bytes:
    """Encode CSV rows as a CP950/Big5 file body (as SOYAL exports them)."""
    return ("\n".join(rows) + "\n").encode("cp950")


def test_decode_file_cp950_round_trips_chinese_name():
    from app.services.nfc_import_service import decode_file

    raw = _cp950(["20260701,072437,F1000118,1,5717003342,王小明"])
    text = decode_file(raw)
    assert "王小明" in text
    assert "F1000118" in text


def test_parse_rows_valid():
    from app.services.nfc_import_service import parse_rows

    text = (
        "20260701,072437,F1000118,1,5717003342,王小明\n"
        "20260701,181045,F1000118,2,5717003342,王小明\n"
    )
    taps, errors = parse_rows(text)
    assert errors == []
    assert len(taps) == 2
    assert taps[0].emp_id == "F1000118"
    assert taps[0].timestamp == datetime.datetime(2026, 7, 1, 7, 24, 37)
    assert taps[0].door_no == "1"
    assert taps[0].card_serial == "5717003342"
    assert taps[1].timestamp == datetime.datetime(2026, 7, 1, 18, 10, 45)


def test_parse_rows_collects_malformed_lines():
    from app.services.nfc_import_service import parse_rows

    text = (
        "20260701,072437,F1000118,1,5717003342,王小明\n"
        "not,enough,fields\n"                              # too few columns
        "20261301,072437,F1000220,1,6108331019,李四\n"     # month 13 → bad date
        "\n"                                               # blank → skipped, no error
    )
    taps, errors = parse_rows(text)
    assert len(taps) == 1
    assert taps[0].emp_id == "F1000118"
    assert len(errors) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_nfc_import_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.nfc_import_service'`.

- [ ] **Step 3: Create the module with the pure functions**

Create `backend/app/services/nfc_import_service.py`:

```python
"""NFC door-tap import service — CP950 parsing + per-side gap-fill backup.

Reads a SOYAL 701 ``YYYYMM.txt`` export (CP950/Big5) and, for each
(emp_id, date), fills ONLY the missing side (clock-in / clock-out) of the day
from the door taps. A real phone punch always wins; NFC never displaces it.
Idempotent: a filled side is never re-filled, so re-importing the cumulative
monthly file is a no-op.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.employee import Employee
from app.repositories import (
    attendance_repository,
    employee_repository,
    system_config_repository,
)
from app.services import reporting_service
from app.utils.taiwan_calendar import (
    DayInfo,
    classify_indexed_date_kind,
    index_calendar,
    parse_calendar_json,
)

CARD_ENCODING = "cp950"
NFC_IP_MARKER = "nfc"


@dataclass(frozen=True)
class NfcTap:
    """One decoded door-tap row."""

    emp_id: str
    timestamp: datetime.datetime
    door_no: str
    card_serial: str
    name: str


def decode_file(raw: bytes) -> str:
    """Decode CP950/Big5 bytes to text.

    ASCII fields (date/time/emp_id/door/serial) are single-byte and always
    safe; ``errors="replace"`` keeps one malformed name byte from killing the
    whole import (names are informational only).
    """
    return raw.decode(CARD_ENCODING, errors="replace")


def parse_rows(text: str) -> tuple[list[NfcTap], list[str]]:
    """Parse decoded CSV text into taps plus a list of malformed raw lines.

    Expected columns: ``date(YYYYMMDD), time(HHMMSS), emp_id, door_no,
    card_serial, name``. Blank lines are skipped silently.
    """
    taps: list[NfcTap] = []
    errors: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(",", 5)
        if len(parts) < 6:
            errors.append(raw_line)
            continue
        date_s, time_s, emp_id, door_no, card_serial, name = (p.strip() for p in parts)
        if not emp_id:
            errors.append(raw_line)
            continue
        try:
            ts = datetime.datetime.strptime(date_s + time_s, "%Y%m%d%H%M%S")
        except ValueError:
            errors.append(raw_line)
            continue
        taps.append(
            NfcTap(
                emp_id=emp_id,
                timestamp=ts,
                door_no=door_no,
                card_serial=card_serial,
                name=name,
            )
        )
    return taps, errors
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_nfc_import_service.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/nfc_import_service.py backend/tests/unit/test_nfc_import_service.py
git commit -m "feat(nfc): add CP950 decode and row parser for door-tap files"
```

---

## Task 3: Per-side gap-fill orchestration

**Files:**
- Modify: `backend/app/services/nfc_import_service.py`
- Test: `backend/tests/unit/test_nfc_import_service.py` (add to the file from Task 2)

**Interfaces:**
- Consumes: `decode_file`, `parse_rows`, `NfcTap` (Task 2); `attendance_repository.create_log` / `find_by_employee_and_date`; `employee_repository.find_by_id`; `system_config_repository.get_workday_calendar`; `reporting_service.generate_daily_summary`; `taiwan_calendar.index_calendar` / `classify_indexed_date_kind` / `parse_calendar_json`.
- Produces:
  - `NfcImportResult` frozen dataclass: `filled_in: int`, `filled_out: int`, `skipped_already_punched: int`, `skipped_terminated: list[str]`, `unknown_emp_ids: list[str]`, `parse_errors: list[str]`, `affected_days: list[str]`.
  - `async import_nfc_file(session: AsyncSession, raw: bytes) -> NfcImportResult`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_nfc_import_service.py`:

```python
async def _non_overridden(db_session: AsyncSession, emp_id: str, date: datetime.date):
    logs = await attendance_repository.find_by_employee_and_date(db_session, emp_id, date)
    return [l for l in logs if not l.is_overridden]


@pytest.mark.asyncio
async def test_import_whole_day_empty_fills_both(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    await db_session.commit()

    raw = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,181045,F1000118,2,5717003342,王小明",
    ])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 1
    assert result.filled_out == 1
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 2
    assert all(l.ip_address == "nfc" for l in logs)
    assert {l.timestamp.time() for l in logs} == {
        datetime.time(7, 24, 37), datetime.time(18, 10, 45),
    }


@pytest.mark.asyncio
async def test_import_single_tap_fills_in_only(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    await db_session.commit()

    raw = _cp950(["20260701,072437,F1000118,1,5717003342,王小明"])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 1
    assert result.filled_out == 0
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_import_fills_missing_out_keeps_phone_in(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    db_session.add(AttendanceLog(
        emp_id="F1000118",
        timestamp=datetime.datetime(2026, 7, 1, 8, 53, 0),
        latitude=25.0, longitude=121.0, accuracy=10.0,
        ip_address="127.0.0.1", work_mode=WorkMode.OFFICE, is_overridden=False,
    ))
    await db_session.commit()

    raw = _cp950(["20260701,181045,F1000118,2,5717003342,王小明"])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 0
    assert result.filled_out == 1
    first = await attendance_repository.find_first_clock_in(
        db_session, "F1000118", datetime.date(2026, 7, 1))
    last = await attendance_repository.find_last_clock_out(
        db_session, "F1000118", datetime.date(2026, 7, 1))
    assert first.timestamp.time() == datetime.time(8, 53)   # phone in preserved
    assert last.timestamp.time() == datetime.time(18, 10, 45)  # nfc out


@pytest.mark.asyncio
async def test_import_does_not_displace_phone_with_earlier_tap(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    db_session.add(AttendanceLog(
        emp_id="F1000118",
        timestamp=datetime.datetime(2026, 7, 1, 8, 53, 0),
        latitude=25.0, longitude=121.0, accuracy=10.0,
        ip_address="127.0.0.1", work_mode=WorkMode.OFFICE, is_overridden=False,
    ))
    await db_session.commit()

    # Only an EARLIER tap exists — cannot become a clock-out (guard: > clock-in).
    raw = _cp950(["20260701,072437,F1000118,1,5717003342,王小明"])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 0
    assert result.filled_out == 0
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_import_complete_day_is_noop(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    for t in (datetime.datetime(2026, 7, 1, 8, 53), datetime.datetime(2026, 7, 1, 18, 2)):
        db_session.add(AttendanceLog(
            emp_id="F1000118", timestamp=t, latitude=25.0, longitude=121.0,
            accuracy=10.0, ip_address="127.0.0.1", work_mode=WorkMode.OFFICE,
            is_overridden=False,
        ))
    await db_session.commit()

    raw = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,190000,F1000118,2,5717003342,王小明",
    ])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 0
    assert result.filled_out == 0
    assert result.skipped_already_punched == 1
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 2  # unchanged


@pytest.mark.asyncio
async def test_import_is_idempotent(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    await db_session.commit()

    raw = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,181045,F1000118,2,5717003342,王小明",
    ])
    await import_nfc_file(db_session, raw)
    second = await import_nfc_file(db_session, raw)

    assert second.filled_in == 0
    assert second.filled_out == 0
    assert second.skipped_already_punched == 1
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 2  # no duplicates


@pytest.mark.asyncio
async def test_import_unknown_emp_id_is_reported_not_fatal(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee("F1000118"))
    await db_session.commit()

    raw = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,073000,GHOST999,1,9999999999,幽靈",
    ])
    result = await import_nfc_file(db_session, raw)

    assert result.unknown_emp_ids == ["GHOST999"]
    assert result.filled_in == 1  # the real employee still filled
    ghost = await _non_overridden(db_session, "GHOST999", datetime.date(2026, 7, 1))
    assert ghost == []


@pytest.mark.asyncio
async def test_import_skips_terminated_employee(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee(
        "F1000118", terminated_at=datetime.datetime(2026, 6, 1)))
    await db_session.commit()

    raw = _cp950(["20260701,072437,F1000118,1,5717003342,王小明"])
    result = await import_nfc_file(db_session, raw)

    assert result.skipped_terminated == ["F1000118"]
    assert result.filled_in == 0
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert logs == []


@pytest.mark.asyncio
async def test_import_weekend_tap_scores_normal(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    await db_session.commit()

    sunday = datetime.date(2026, 7, 5)
    assert sunday.weekday() == 6  # Sunday → 例假日 → NORMAL, not LATE/EARLY
    raw = _cp950([
        "20260705,100000,F1000118,1,5717003342,王小明",
        "20260705,140000,F1000118,2,5717003342,王小明",
    ])
    await import_nfc_file(db_session, raw)

    summaries = await summary_repository.find_by_employee(
        db_session, "F1000118", start_date=sunday, end_date=sunday)
    assert len(summaries) == 1
    assert summaries[0].status == AttendanceStatus.NORMAL
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/unit/test_nfc_import_service.py -v`
Expected: the 9 new `test_import_*` tests FAIL with `ImportError: cannot import name 'import_nfc_file'`. (The 3 Task-2 tests still pass.)

- [ ] **Step 3: Add the orchestration to the service**

Append to `backend/app/services/nfc_import_service.py`:

```python
@dataclass(frozen=True)
class NfcImportResult:
    """Immutable summary of one import run."""

    filled_in: int
    filled_out: int
    skipped_already_punched: int
    skipped_terminated: list[str]
    unknown_emp_ids: list[str]
    parse_errors: list[str]
    affected_days: list[str]


async def _load_calendar_index(
    session: AsyncSession, year: int
) -> dict[datetime.date, DayInfo]:
    """Cached Taiwan calendar as date→DayInfo for O(1) day_kind lookups.

    Cached-only (no CDN fetch) — mirrors attendance_service; a cold cache
    degrades to the pure weekday fallback inside classify_indexed_date_kind.
    """
    cached = await system_config_repository.get_workday_calendar(session, year)
    data = parse_calendar_json(cached.get("entries", [])) if cached else []
    return index_calendar(data)


def _group_by_emp_date(
    taps: list[NfcTap],
) -> dict[tuple[str, datetime.date], list[NfcTap]]:
    groups: dict[tuple[str, datetime.date], list[NfcTap]] = {}
    for tap in taps:
        groups.setdefault((tap.emp_id, tap.timestamp.date()), []).append(tap)
    return groups


def _make_nfc_log(emp_id: str, ts: datetime.datetime) -> AttendanceLog:
    return AttendanceLog(
        emp_id=emp_id,
        timestamp=ts,
        latitude=0.0,
        longitude=0.0,
        accuracy=0.0,
        ip_address=NFC_IP_MARKER,
        work_mode=WorkMode.OFFICE,
        is_overridden=False,
    )


async def import_nfc_file(session: AsyncSession, raw: bytes) -> NfcImportResult:
    """Decode, parse, and per-side gap-fill a SOYAL door-tap export."""
    taps, parse_errors = parse_rows(decode_file(raw))
    groups = _group_by_emp_date(taps)

    filled_in = 0
    filled_out = 0
    skipped_already_punched = 0
    skipped_terminated: list[str] = []
    unknown_emp_ids: list[str] = []
    affected_days: list[str] = []

    # Preload calendars for every touched year so summary regen gets the
    # calendar-accurate day_kind (補班 Saturdays, weekday holidays) without N+1.
    calendars = {
        year: await _load_calendar_index(session, year)
        for year in {date.year for (_emp, date) in groups}
    }
    employee_cache: dict[str, Employee | None] = {}

    for (emp_id, date), day_taps in sorted(
        groups.items(), key=lambda kv: (kv[0][1], kv[0][0])
    ):
        if emp_id not in employee_cache:
            employee_cache[emp_id] = await employee_repository.find_by_id(
                session, emp_id
            )
        employee = employee_cache[emp_id]
        if employee is None:
            if emp_id not in unknown_emp_ids:
                unknown_emp_ids.append(emp_id)
            continue
        if employee.terminated_at is not None and employee.terminated_at.date() <= date:
            if emp_id not in skipped_terminated:
                skipped_terminated.append(emp_id)
            continue

        existing = await attendance_repository.find_by_employee_and_date(
            session, emp_id, date
        )
        non_overridden = [log for log in existing if not log.is_overridden]
        has_in = len(non_overridden) >= 1
        has_out = len(non_overridden) >= 2

        if has_in and has_out:
            skipped_already_punched += 1
            continue

        day_taps.sort(key=lambda tap: tap.timestamp)
        earliest = day_taps[0].timestamp
        latest = day_taps[-1].timestamp
        did_fill = False

        if has_in:
            effective_in = min(log.timestamp for log in non_overridden)
        else:
            await attendance_repository.create_log(
                session, _make_nfc_log(emp_id, earliest)
            )
            filled_in += 1
            did_fill = True
            effective_in = earliest

        if not has_out and latest > effective_in:
            await attendance_repository.create_log(
                session, _make_nfc_log(emp_id, latest)
            )
            filled_out += 1
            did_fill = True

        if did_fill:
            day_kind = classify_indexed_date_kind(calendars[date.year], date)
            await reporting_service.generate_daily_summary(
                session, emp_id, date, day_kind=day_kind
            )
            affected_days.append(f"{emp_id} {date.isoformat()}")

    return NfcImportResult(
        filled_in=filled_in,
        filled_out=filled_out,
        skipped_already_punched=skipped_already_punched,
        skipped_terminated=skipped_terminated,
        unknown_emp_ids=unknown_emp_ids,
        parse_errors=parse_errors,
        affected_days=affected_days,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_nfc_import_service.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/nfc_import_service.py backend/tests/unit/test_nfc_import_service.py
git commit -m "feat(nfc): per-side gap-fill import orchestration"
```

---

## Task 4: Response schema

**Files:**
- Create: `backend/app/schemas/nfc.py`

**Interfaces:**
- Produces: `NfcImportResponse` (Pydantic `BaseModel`) with the same 7 fields as `NfcImportResult`.

- [ ] **Step 1: Create the schema**

Create `backend/app/schemas/nfc.py`:

```python
"""Pydantic schema for the NFC import endpoint response."""

from pydantic import BaseModel


class NfcImportResponse(BaseModel):
    """Report returned by POST /api/nfc/import."""

    filled_in: int
    filled_out: int
    skipped_already_punched: int
    skipped_terminated: list[str]
    unknown_emp_ids: list[str]
    parse_errors: list[str]
    affected_days: list[str]
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from app.schemas.nfc import NfcImportResponse; print(NfcImportResponse.model_fields.keys())"`
Expected: prints the 7 field names, no exception.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/nfc.py
git commit -m "feat(nfc): add NfcImportResponse schema"
```

---

## Task 5: Router + API-key auth + registration

**Files:**
- Create: `backend/app/routers/nfc.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_nfc_import_api.py`

**Interfaces:**
- Consumes: `settings.nfc_import_api_key` (Task 1); `nfc_import_service.import_nfc_file` (Task 3); `NfcImportResponse` (Task 4); `get_db`.
- Produces: `POST /api/nfc/import`; dependency `require_nfc_api_key`.

- [ ] **Step 1: Write the failing integration tests**

Create `backend/tests/integration/test_nfc_import_api.py`:

```python
"""Integration tests for POST /api/nfc/import."""

import datetime

import pytest

from app.config import settings
from app.models.employee import Employee, Role


def _make_employee(emp_id: str = "F1000118") -> Employee:
    return Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )


def _cp950(rows: list[str]) -> bytes:
    return ("\n".join(rows) + "\n").encode("cp950")


@pytest.mark.asyncio
async def test_import_missing_key_is_401(client, monkeypatch):
    monkeypatch.setattr(settings, "nfc_import_api_key", "secret-key")
    resp = await client.post("/api/nfc/import", content=_cp950([]))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_wrong_key_is_401(client, monkeypatch):
    monkeypatch.setattr(settings, "nfc_import_api_key", "secret-key")
    resp = await client.post(
        "/api/nfc/import",
        content=_cp950([]),
        headers={"X-NFC-API-Key": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_not_configured_is_503(client, monkeypatch):
    monkeypatch.setattr(settings, "nfc_import_api_key", "")
    resp = await client.post(
        "/api/nfc/import",
        content=_cp950([]),
        headers={"X-NFC-API-Key": "anything"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_import_success(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "nfc_import_api_key", "secret-key")
    db_session.add(_make_employee())
    await db_session.commit()

    body = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,181045,F1000118,2,5717003342,王小明",
    ])
    resp = await client.post(
        "/api/nfc/import",
        content=body,
        headers={"X-NFC-API-Key": "secret-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filled_in"] == 1
    assert data["filled_out"] == 1
    assert data["affected_days"] == ["F1000118 2026-07-01"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/integration/test_nfc_import_api.py -v`
Expected: FAIL — 404 (route not registered) / import errors.

- [ ] **Step 3: Create the router**

Create `backend/app/routers/nfc.py`:

```python
"""NFC door-tap import router — machine-to-machine, API-key authenticated."""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.nfc import NfcImportResponse
from app.services import nfc_import_service

router = APIRouter(prefix="/api/nfc", tags=["nfc"])


async def require_nfc_api_key(
    x_nfc_api_key: str | None = Header(default=None, alias="X-NFC-API-Key"),
) -> None:
    """Reject unless the request carries the configured NFC import API key.

    Returns 503 when the feature is unconfigured (empty key) so an empty
    secret can never accidentally authenticate an empty header.
    """
    configured = settings.nfc_import_api_key
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NFC import is not configured",
        )
    if not x_nfc_api_key or not hmac.compare_digest(x_nfc_api_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing NFC API key",
        )


@router.post("/import", response_model=NfcImportResponse)
async def import_nfc(
    request: Request,
    _auth: None = Depends(require_nfc_api_key),
    session: AsyncSession = Depends(get_db),
) -> NfcImportResponse:
    """Ingest a raw CP950 door-tap file and per-side gap-fill missing punches."""
    raw = await request.body()
    result = await nfc_import_service.import_nfc_file(session, raw)
    return NfcImportResponse(
        filled_in=result.filled_in,
        filled_out=result.filled_out,
        skipped_already_punched=result.skipped_already_punched,
        skipped_terminated=result.skipped_terminated,
        unknown_emp_ids=result.unknown_emp_ids,
        parse_errors=result.parse_errors,
        affected_days=result.affected_days,
    )
```

- [ ] **Step 4: Register the router in `main.py`**

In `backend/app/main.py`, add `nfc` to the router import block (keep alphabetical order — between `monthly_submissions` and `org_hierarchy`):

```python
from app.routers import (
    attendance,
    auth,
    employees,
    leave_types,
    monthly_submissions,
    nfc,
    org_hierarchy,
    reasons,
    reports,
    system_config,
)
```

And add the include call alongside the others (after `app.include_router(monthly_submissions.router)`):

```python
app.include_router(nfc.router)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/integration/test_nfc_import_api.py -v`
Expected: 4 passed.

- [ ] **Step 6: Run the full backend suite (no regressions)**

Run: `pytest -q`
Expected: all pass (previous count + 16 new NFC tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/nfc.py backend/app/main.py backend/tests/integration/test_nfc_import_api.py
git commit -m "feat(nfc): add POST /api/nfc/import endpoint with API-key auth"
```

---

## Task 6: Door-side PowerShell push agent

**Files:**
- Create: `tools/nfc-agent/push-nfc.ps1`
- Create: `tools/nfc-agent/README.md`

**Interfaces:**
- Consumes: `POST /api/nfc/import` (Task 5) via HTTPS + `X-NFC-API-Key`.
- Produces: a scheduled push of `YYYYMM.txt` (and last month's file on the 1st).

*(No automated test — this runs on the door PC. The task deliverable is the script + verification runbook in the README.)*

- [ ] **Step 1: Create the push script**

Create `tools/nfc-agent/push-nfc.ps1`:

```powershell
# push-nfc.ps1 — read the current-month SOYAL 701 export and POST it to the
# GoGoFresh attendance backend for NFC gap-fill backup.
#
# Runs daily via Task Scheduler (~00:20, after the 00:10 file generation).
# Outbound HTTPS only; needs no inbound/firewall changes on the office LAN.

param(
    [string]$Folder  = "C:\Users\ltre5\OneDrive\桌面\門禁",
    [string]$ApiUrl  = "https://www.gogoffcc.com/gogoffcc-arms/api/nfc/import",
    [string]$ApiKey  = $env:NFC_IMPORT_API_KEY,
    [string]$LogFile = "$PSScriptRoot\push-nfc.log"
)

function Write-Log([string]$msg) {
    Add-Content -Path $LogFile -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

if (-not $ApiKey) {
    Write-Log "ERROR: NFC_IMPORT_API_KEY not set"
    exit 1
}

function Send-File([string]$fileName) {
    $path = Join-Path $Folder $fileName
    if (-not (Test-Path $path)) {
        Write-Log "SKIP: $fileName not found"
        return
    }
    $bytes = [System.IO.File]::ReadAllBytes($path)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $resp = Invoke-RestMethod -Uri $ApiUrl -Method Post -Body $bytes `
                -ContentType "application/octet-stream" `
                -Headers @{ "X-NFC-API-Key" = $ApiKey } -TimeoutSec 60
            Write-Log ("OK {0}: in={1} out={2} skipped={3} unknown=[{4}] terminated=[{5}]" -f `
                $fileName, $resp.filled_in, $resp.filled_out, $resp.skipped_already_punched, `
                ($resp.unknown_emp_ids -join "|"), ($resp.skipped_terminated -join "|"))
            return
        } catch {
            Write-Log ("ERROR {0} attempt {1}: {2}" -f $fileName, $attempt, $_.Exception.Message)
            Start-Sleep -Seconds (5 * $attempt)
        }
    }
    Write-Log "GIVE UP: $fileName after 3 attempts"
}

$now = Get-Date
Send-File ("{0:yyyyMM}.txt" -f $now)
# On the 1st, also resend last month's file to catch the final day's late taps.
if ($now.Day -eq 1) {
    Send-File ("{0:yyyyMM}.txt" -f $now.AddMonths(-1))
}
```

- [ ] **Step 2: Create the README**

Create `tools/nfc-agent/README.md`:

````markdown
# NFC door-tap push agent

Pushes the SOYAL 701 `YYYYMM.txt` export to the attendance backend for
per-side gap-fill. See `docs/superpowers/specs/2026-07-01-nfc-punch-backup-design.md`.

## Install on the door PC (`DESKTOP-MMGK6PJ`)

1. Copy `push-nfc.ps1` to e.g. `C:\nfc-agent\push-nfc.ps1`.
2. Set the API key as a machine environment variable (matches backend
   `NFC_IMPORT_API_KEY`):

   ```powershell
   [Environment]::SetEnvironmentVariable("NFC_IMPORT_API_KEY", "<the-secret>", "Machine")
   ```

3. Register the daily scheduled task (runs 00:20, after the 00:10 export):

   ```cmd
   schtasks /Create /SC DAILY /ST 00:20 /RL HIGHEST /TN "GoGoFresh NFC Push" ^
     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\nfc-agent\push-nfc.ps1"
   ```

## Verify

- Run once by hand and check the log:

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File C:\nfc-agent\push-nfc.ps1
  Get-Content C:\nfc-agent\push-nfc.log -Tail 5
  ```

- Expect a line like `OK 202607.txt: in=3 out=1 skipped=10 unknown=[] terminated=[]`.
- End-to-end: tap test card `02400:09483`, wait for the next export, run the
  script, then confirm the punch appears on that employee's day in the app.

## Notes

- Params can be overridden, e.g. `push-nfc.ps1 -Folder "D:\door" -ApiUrl "https://…/api/nfc/import"`.
- The door PC's DHCP IP is irrelevant — this only makes outbound calls.
- Sends the file bytes raw (CP950); the backend does the decoding.
````

- [ ] **Step 3: Lint-check the script parses**

Run: `pwsh -NoProfile -Command "$null = [System.Management.Automation.Language.Parser]::ParseFile('tools/nfc-agent/push-nfc.ps1', [ref]$null, [ref]$null); 'parse-ok'"`
Expected: prints `parse-ok` (no parser errors). *(If `pwsh` is unavailable, open the file and eyeball it — no test infra depends on it.)*

- [ ] **Step 4: Commit**

```bash
git add tools/nfc-agent/push-nfc.ps1 tools/nfc-agent/README.md
git commit -m "feat(nfc): add door-PC PowerShell push agent and README"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Covered by |
|---|---|
| §3 format / CP950 decode | Task 2 (`decode_file`, `parse_rows`) |
| §5 in/out by time | Task 3 (`earliest`/`latest`) |
| §6 per-side gap-fill + clock-out guard | Task 3 (`import_nfc_file`, `latest > effective_in`) |
| §7 idempotency (filled side never re-filled) | Task 3 + `test_import_is_idempotent` |
| §8 backend layers + `ip_address="nfc"` marker | Tasks 3–5 |
| §9 API-key security (`X-NFC-API-Key`, 401/503) | Task 5 |
| §10 report shape | Task 3 `NfcImportResult` + Task 4 schema |
| §11 push agent + month-rollover dual-send | Task 6 |
| §12 weekend/holiday NORMAL | Task 3 + `test_import_weekend_tap_scores_normal` |
| §13 unknown / terminated / malformed | Task 3 tests |
| §14 tests | Tasks 2/3/5 |
| §15 env var / no migration | Task 1 |

No gaps.

**2. Placeholder scan:** none — every step has real code/commands.

**3. Type consistency:** `NfcImportResult` (Task 3) and `NfcImportResponse` (Task 4) share the same 7 field names; the router (Task 5) maps them 1:1. `import_nfc_file(session, raw) -> NfcImportResult` used consistently. `_make_nfc_log` marker `"nfc"` matches the `ip_address == "nfc"` test assertions.

---

## Notes for the implementer

- Run backend commands from `backend/` using the native venv (`backend\.venv`), not Docker.
- `attendance_repository.create_log` commits internally (existing behavior) — that's why the tests can read logs back immediately.
- Do **not** add a `source` DB column — the `ip_address="nfc"` marker is intentional for v1.
- Keep `main` untouched; all work stays on `feature/nfc-punch-backup`.
