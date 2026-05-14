# Leave Remarks, Monthly Submission & Export Refinements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add leave-type remarks on daily summaries (new `LEAVE` status), per-employee monthly submission flag, Chinese-ized export with shift-time + remark + submission columns, monthly-override warning modal, and revoke HR's employee-delete permission (ADMIN-only).

**Architecture:** Spec at `docs/superpowers/specs/2026-05-14-leave-remarks-monthly-submission-design.md`. Five sub-features ship in one coordinated migration. Two new columns on `daily_attendance_summaries` (`leave_type`, `remark`); new table `monthly_submissions`; new `LEAVE` enum value; new `system_config.leave_types` seed. `calculate_status` gains a `leave_type` parameter that short-circuits to `LEAVE`. Reports get a tri-valued `submission_filter` param. `attendance_reasons` is untouched — it lives parallel to the new remark column with separate display.

**Tech Stack:** FastAPI · SQLAlchemy/SQLModel · Alembic · PostgreSQL · Pydantic · Next.js App Router · React · TailwindCSS · next-intl · Vitest · Playwright · pytest

---

## File Structure

### New files
| Path | Responsibility |
|---|---|
| `backend/alembic/versions/f6a7b8c9d0e1_leave_remarks_and_monthly_submission.py` | Migration: LEAVE enum, 2 columns, monthly_submissions table, seed leave_types |
| `backend/app/models/monthly_submission.py` | SQLModel for monthly_submissions table |
| `backend/app/repositories/monthly_submission_repository.py` | CRUD + upsert + list_by_month |
| `backend/app/services/monthly_submission_service.py` | `submit_month`, `get_submission_status`, `is_submitted` |
| `backend/app/routers/monthly_submissions.py` | POST/GET endpoints |
| `backend/app/routers/leave_types.py` | GET/PUT `/api/admin/leave-types` |
| `backend/app/schemas/monthly_submission.py` | Pydantic request/response models |
| `backend/app/schemas/leave_types.py` | Pydantic schema for leave types config |
| `backend/tests/unit/test_monthly_submission_repository.py` | Repository unit tests |
| `backend/tests/unit/test_calculate_status_leave.py` | LEAVE branch unit tests |
| `backend/tests/integration/test_monthly_submissions_api.py` | Submission endpoint tests |
| `backend/tests/integration/test_leave_types_api.py` | Leave-type config tests |
| `backend/tests/integration/test_reports_submission_filter.py` | submission_filter behavior tests |
| `backend/tests/integration/test_employees_delete_permission.py` | DELETE permission downgrade test |
| `backend/tests/integration/test_export_chinese.py` | Chinese-ized export tests |
| `frontend/src/components/monthly-override/RemarkCell.tsx` | Per-day remark cell (dropdown + text) |
| `frontend/src/components/monthly-override/WarningModal.tsx` | Tardy-day warning modal |
| `frontend/src/components/admin/LeaveTypeManager.tsx` | Admin UI for leave types |
| `frontend/src/lib/api/monthly-submissions.ts` | Client for submissions API |
| `frontend/src/lib/api/leave-types.ts` | Client for leave-types API |
| `frontend/tests/unit/RemarkCell.test.tsx` | Component test |
| `frontend/tests/unit/WarningModal.test.tsx` | Component test |
| `frontend/tests/unit/reports-submission-filter.test.tsx` | Reports page filter test |
| `frontend/tests/e2e/leave-and-submit.spec.ts` | Playwright E2E |

### Modified files
| Path | Change |
|---|---|
| `backend/app/models/daily_attendance_summary.py` | Add `LEAVE` enum value + `leave_type` + `remark` columns |
| `backend/app/repositories/summary_repository.py` | `upsert_summary` accepts `leave_type`/`remark`; new `set_remark_fields` helper |
| `backend/app/services/reporting_service.py` | `calculate_status` takes `leave_type`; `generate_daily_summary` reads existing remark; `get_daily_report`/`export_attendance` take `submission_filter`; export Chinese-ized + new columns |
| `backend/app/services/permission_service.py` | Add `DELETE_EMPLOYEE` constant; HR set does NOT include it; ADMIN does |
| `backend/app/services/attendance_service.py` | `bulk_override_punches` accepts `leave_type`/`remark` per entry; persists via summary |
| `backend/app/schemas/bulk_override.py` | `BulkOverrideEntry` adds `leave_type` + `remark` optional fields |
| `backend/app/routers/employees.py` | `DELETE /{emp_id}` `require_role(Role.HR)` → `require_role(Role.ADMIN)` |
| `backend/app/routers/attendance.py` | `bulk_override` passes new fields through |
| `backend/app/routers/reports.py` | `daily` and `export` accept `submission_filter` query param |
| `backend/app/main.py` | Register `monthly_submissions` and `leave_types` routers |
| `frontend/src/messages/en.json` | New i18n keys |
| `frontend/src/messages/zh.json` | New i18n keys |
| `frontend/src/app/dashboard/monthly-override/page.tsx` | Remark column, `本月送單` button, modal integration |
| `frontend/src/app/reports/page.tsx` | New 3 columns, submission filter dropdown |
| `frontend/src/app/admin/page.tsx` (or wherever admin tabs live) | Add `假別管理` tab; conditional delete button |
| `frontend/src/types/index.ts` (or similar) | New TS types for leave_type, remark, submission_status |
| `CLAUDE.md` | Add decision #30 documenting this feature set |

---

## Conventions used throughout this plan

- **Commits**: Conventional Commits format (`feat:`, `fix:`, `test:`, `refactor:`, `chore:`, `docs:`). One commit per task unless noted.
- **Backend tests**: `pytest backend/tests/path/test_file.py::test_name -v` from repo root, after `cd backend`.
- **Frontend tests**: `npx vitest run path/to/test.test.tsx` from `frontend/`.
- **E2E**: `npx playwright test path/to/file.spec.ts` from `frontend/`.
- **Migration**: `cd backend && alembic upgrade head` (and `alembic downgrade -1` to verify reversibility).
- **TDD**: each task writes the failing test FIRST, runs to confirm RED, then implements minimal code to GREEN.

---

## Phase A — Database Schema & Models

### Task 1: Alembic migration

**Files:**
- Create: `backend/alembic/versions/f6a7b8c9d0e1_leave_remarks_and_monthly_submission.py`

- [ ] **Step 1: Create the migration file with this exact content**

```python
"""leave remarks columns, monthly_submissions table, LEAVE enum, leave_types seed

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-14 09:00:00.000000

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_LEAVE_TYPES = [
    "特休", "病假", "事假", "婚假", "喪假", "產假", "公假", "出差", "補休",
]


def upgrade() -> None:
    # 1. Add LEAVE enum value
    op.execute("ALTER TYPE attendancestatus ADD VALUE IF NOT EXISTS 'LEAVE'")

    # 2. Add leave_type + remark columns to daily_attendance_summaries
    op.add_column(
        "daily_attendance_summaries",
        sa.Column("leave_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "daily_attendance_summaries",
        sa.Column("remark", sa.String(length=500), nullable=True),
    )

    # 3. Create monthly_submissions table
    op.create_table(
        "monthly_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("emp_id", sa.String(), sa.ForeignKey("employees.emp_id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_submissions_month"),
        sa.UniqueConstraint("emp_id", "year", "month", name="uq_monthly_submission"),
    )
    op.create_index(
        "idx_monthly_submissions_lookup",
        "monthly_submissions",
        ["year", "month"],
    )

    # 4. Seed leave_types into system_config (idempotent)
    op.execute(
        sa.text(
            "INSERT INTO system_config (key, value) "
            "VALUES (:key, CAST(:value AS JSON)) "
            "ON CONFLICT (key) DO NOTHING"
        ).bindparams(
            key="leave_types",
            value=json.dumps({"types": DEFAULT_LEAVE_TYPES}),
        )
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_config WHERE key = 'leave_types'")
    op.drop_index("idx_monthly_submissions_lookup", table_name="monthly_submissions")
    op.drop_table("monthly_submissions")
    op.drop_column("daily_attendance_summaries", "remark")
    op.drop_column("daily_attendance_summaries", "leave_type")
    # LEAVE enum value cannot be removed without rebuilding the type — left as no-op.
```

- [ ] **Step 2: Run migration**

```bash
cd backend && alembic upgrade head
```
Expected: no error; new objects created.

- [ ] **Step 3: Verify downgrade works**

```bash
cd backend && alembic downgrade -1 && alembic upgrade head
```
Expected: both succeed.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/f6a7b8c9d0e1_leave_remarks_and_monthly_submission.py
git commit -m "feat(db): add leave_type/remark columns, monthly_submissions table, LEAVE enum, leave_types seed"
```

---

### Task 2: Add LEAVE to AttendanceStatus enum + columns to DailyAttendanceSummary model

**Files:**
- Modify: `backend/app/models/daily_attendance_summary.py`
- Test: `backend/tests/unit/test_models.py` (add a test there or create dedicated)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_calculate_status_leave.py`:

```python
"""Tests for LEAVE enum value and remark columns."""
from app.models.daily_attendance_summary import AttendanceStatus, DailyAttendanceSummary


def test_leave_enum_value_exists():
    assert AttendanceStatus.LEAVE.value == "LEAVE"


def test_summary_model_has_leave_type_and_remark():
    summary = DailyAttendanceSummary(
        emp_id="E001",
        date="2026-05-14",
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休",
        remark="上午",
    )
    assert summary.leave_type == "特休"
    assert summary.remark == "上午"
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
cd backend && pytest tests/unit/test_calculate_status_leave.py -v
```
Expected: FAIL — `LEAVE` not in enum, `leave_type`/`remark` not on model.

- [ ] **Step 3: Update model**

Replace the body of `backend/app/models/daily_attendance_summary.py` with:

```python
"""DailyAttendanceSummary model with AttendanceStatus enum."""

import datetime
import enum
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class AttendanceStatus(str, enum.Enum):
    """Daily attendance status classification."""

    NORMAL = "NORMAL"
    LATE = "LATE"
    EARLY_LEAVE = "EARLY_LEAVE"
    LATE_AND_EARLY_LEAVE = "LATE_AND_EARLY_LEAVE"
    ABNORMAL = "ABNORMAL"
    ABSENT = "ABSENT"
    LEAVE = "LEAVE"


class DailyAttendanceSummary(SQLModel, table=True):
    """Daily attendance summaries — one row per employee per date."""

    __tablename__ = "daily_attendance_summaries"
    __table_args__ = (
        sa.UniqueConstraint("emp_id", "date", name="uq_summary_emp_date"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    emp_id: str = Field(foreign_key="employees.emp_id")
    date: datetime.date
    first_clock_in: Optional[datetime.datetime] = Field(default=None)
    last_clock_out: Optional[datetime.datetime] = Field(default=None)
    status: AttendanceStatus = Field(
        sa_column=sa.Column(sa.Enum(AttendanceStatus), nullable=False)
    )
    leave_type: Optional[str] = Field(default=None, max_length=50)
    remark: Optional[str] = Field(default=None, max_length=500)
```

- [ ] **Step 4: Run test (expect PASS)**

```bash
cd backend && pytest tests/unit/test_calculate_status_leave.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/daily_attendance_summary.py backend/tests/unit/test_calculate_status_leave.py
git commit -m "feat(model): add LEAVE status + leave_type/remark to DailyAttendanceSummary"
```

---

### Task 3: MonthlySubmission model

**Files:**
- Create: `backend/app/models/monthly_submission.py`
- Modify: `backend/app/models/__init__.py` (export the model)
- Test: extend `backend/tests/unit/test_monthly_submission_repository.py` (next task) — for now, just import smoke test

- [ ] **Step 1: Create the model**

`backend/app/models/monthly_submission.py`:

```python
"""MonthlySubmission model — per-employee per-month confirmation flag."""

import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class MonthlySubmission(SQLModel, table=True):
    """One row per (employee, year, month) marking the month as 'submitted'."""

    __tablename__ = "monthly_submissions"
    __table_args__ = (
        sa.UniqueConstraint("emp_id", "year", "month", name="uq_monthly_submission"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_submissions_month"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    emp_id: str = Field(foreign_key="employees.emp_id")
    year: int
    month: int
    submitted_at: datetime.datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
```

- [ ] **Step 2: Export from `__init__.py`**

Add to `backend/app/models/__init__.py` (preserving existing exports):

```python
from app.models.monthly_submission import MonthlySubmission  # noqa: F401
```

(Read the file first; preserve existing imports and `__all__` if present.)

- [ ] **Step 3: Smoke import**

```bash
cd backend && python -c "from app.models.monthly_submission import MonthlySubmission; print(MonthlySubmission.__tablename__)"
```
Expected: prints `monthly_submissions`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/monthly_submission.py backend/app/models/__init__.py
git commit -m "feat(model): add MonthlySubmission"
```

---

## Phase B — Backend Repositories

### Task 4: monthly_submission_repository

**Files:**
- Create: `backend/app/repositories/monthly_submission_repository.py`
- Create: `backend/tests/unit/test_monthly_submission_repository.py`
- Modify: `backend/app/repositories/__init__.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/unit/test_monthly_submission_repository.py`:

```python
"""Unit tests for monthly_submission_repository."""
import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import monthly_submission_repository as repo
from tests.conftest import seed_employee  # existing helper; if missing, use the standard fixture pattern in other unit tests


@pytest.mark.asyncio
async def test_upsert_creates_new_row(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E001")
    row = await repo.upsert(db_session, emp_id="E001", year=2026, month=5)
    assert row.emp_id == "E001"
    assert row.year == 2026
    assert row.month == 5
    assert row.submitted_at is not None


@pytest.mark.asyncio
async def test_upsert_refreshes_timestamp_on_resubmit(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E001")
    first = await repo.upsert(db_session, emp_id="E001", year=2026, month=5)
    first_ts = first.submitted_at
    second = await repo.upsert(db_session, emp_id="E001", year=2026, month=5)
    assert second.id == first.id  # same row
    assert second.submitted_at >= first_ts


@pytest.mark.asyncio
async def test_find_returns_none_when_absent(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E002")
    result = await repo.find(db_session, emp_id="E002", year=2026, month=5)
    assert result is None


@pytest.mark.asyncio
async def test_find_returns_row(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E003")
    await repo.upsert(db_session, emp_id="E003", year=2026, month=5)
    result = await repo.find(db_session, emp_id="E003", year=2026, month=5)
    assert result is not None
    assert result.emp_id == "E003"


@pytest.mark.asyncio
async def test_is_submitted_set(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E004")
    await seed_employee(db_session, emp_id="E005")
    await repo.upsert(db_session, emp_id="E004", year=2026, month=5)
    submitted_ids = await repo.submitted_emp_ids(db_session, year=2026, month=5)
    assert "E004" in submitted_ids
    assert "E005" not in submitted_ids
```

> If `seed_employee` does not already exist in `tests/conftest.py`, use whatever fixture pattern peer tests use (e.g. directly construct `Employee` instances and `session.add`). Check `backend/tests/unit/test_summary_repository.py` for the established pattern.

- [ ] **Step 2: Run tests (expect FAIL — module not found)**

```bash
cd backend && pytest tests/unit/test_monthly_submission_repository.py -v
```
Expected: FAIL with ImportError on `monthly_submission_repository`.

- [ ] **Step 3: Implement the repository**

`backend/app/repositories/monthly_submission_repository.py`:

```python
"""Monthly submission repository — async data access."""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monthly_submission import MonthlySubmission


async def upsert(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> MonthlySubmission:
    """Insert or refresh the (emp_id, year, month) row's submitted_at."""
    statement = select(MonthlySubmission).where(
        MonthlySubmission.emp_id == emp_id,
        MonthlySubmission.year == year,
        MonthlySubmission.month == month,
    )
    result = await session.execute(statement)
    existing = result.scalar_one_or_none()

    now = datetime.datetime.now(datetime.UTC)

    if existing is not None:
        existing.submitted_at = now
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    row = MonthlySubmission(
        emp_id=emp_id, year=year, month=month, submitted_at=now
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def find(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> MonthlySubmission | None:
    statement = select(MonthlySubmission).where(
        MonthlySubmission.emp_id == emp_id,
        MonthlySubmission.year == year,
        MonthlySubmission.month == month,
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def submitted_emp_ids(
    session: AsyncSession,
    year: int,
    month: int,
) -> set[str]:
    """Return the set of emp_ids that have submitted for the given (year, month)."""
    statement = select(MonthlySubmission.emp_id).where(
        MonthlySubmission.year == year,
        MonthlySubmission.month == month,
    )
    result = await session.execute(statement)
    return set(result.scalars().all())


async def list_by_month(
    session: AsyncSession,
    year: int,
    month: int,
) -> list[MonthlySubmission]:
    """Return all submission rows for the given (year, month), ordered by emp_id."""
    statement = (
        select(MonthlySubmission)
        .where(MonthlySubmission.year == year, MonthlySubmission.month == month)
        .order_by(MonthlySubmission.emp_id)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())
```

- [ ] **Step 4: Wire into repositories `__init__.py`**

Append to `backend/app/repositories/__init__.py`:
```python
from app.repositories import monthly_submission_repository  # noqa: F401
```
(Follow the existing pattern in that file.)

- [ ] **Step 5: Run tests (expect PASS)**

```bash
cd backend && pytest tests/unit/test_monthly_submission_repository.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/monthly_submission_repository.py \
        backend/app/repositories/__init__.py \
        backend/tests/unit/test_monthly_submission_repository.py
git commit -m "feat(repo): add monthly_submission_repository with upsert/find/submitted_emp_ids/list_by_month"
```

---

### Task 5: Extend summary_repository.upsert_summary with leave_type/remark

**Files:**
- Modify: `backend/app/repositories/summary_repository.py`
- Modify: `backend/tests/unit/test_summary_repository.py` (or whatever the existing summary repo test file is — find it first)

- [ ] **Step 1: Find the existing summary repo test file**

```bash
ls backend/tests/unit/ | grep -i summary
```
Use that file. If none exists, create `backend/tests/unit/test_summary_repository.py`.

- [ ] **Step 2: Add failing tests for new params**

Append to the summary repo test file:

```python
@pytest.mark.asyncio
async def test_upsert_summary_persists_leave_type_and_remark(db_session):
    await seed_employee(db_session, emp_id="E010")
    summary = await summary_repository.upsert_summary(
        db_session,
        emp_id="E010",
        date=datetime.date(2026, 5, 14),
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休",
        remark="上午",
    )
    assert summary.leave_type == "特休"
    assert summary.remark == "上午"


@pytest.mark.asyncio
async def test_upsert_summary_updates_remark_fields_on_existing_row(db_session):
    await seed_employee(db_session, emp_id="E011")
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E011",
        date=datetime.date(2026, 5, 14),
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.ABSENT,
    )
    updated = await summary_repository.upsert_summary(
        db_session,
        emp_id="E011",
        date=datetime.date(2026, 5, 14),
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="病假",
        remark=None,
    )
    assert updated.status == AttendanceStatus.LEAVE
    assert updated.leave_type == "病假"
    assert updated.remark is None
```

- [ ] **Step 3: Run tests (expect FAIL on signature)**

```bash
cd backend && pytest tests/unit/test_summary_repository.py -v
```
Expected: FAIL with `unexpected keyword argument 'leave_type'`.

- [ ] **Step 4: Update repository**

Replace `upsert_summary` in `backend/app/repositories/summary_repository.py` with:

```python
async def upsert_summary(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
    first_clock_in: datetime.datetime | None,
    last_clock_out: datetime.datetime | None,
    status: AttendanceStatus,
    leave_type: str | None = None,
    remark: str | None = None,
) -> DailyAttendanceSummary:
    """Insert or update a daily attendance summary by (emp_id, date)."""
    statement = select(DailyAttendanceSummary).where(
        DailyAttendanceSummary.emp_id == emp_id,
        DailyAttendanceSummary.date == date,
    )
    result = await session.execute(statement)
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.first_clock_in = first_clock_in
        existing.last_clock_out = last_clock_out
        existing.status = status
        existing.leave_type = leave_type
        existing.remark = remark
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    summary = DailyAttendanceSummary(
        emp_id=emp_id,
        date=date,
        first_clock_in=first_clock_in,
        last_clock_out=last_clock_out,
        status=status,
        leave_type=leave_type,
        remark=remark,
    )
    session.add(summary)
    await session.commit()
    await session.refresh(summary)
    return summary
```

> Note: this is a breaking signature extension for callers that omit the keyword args — they'll just get NULLs, which preserves existing behavior. The defaults make it backward-compatible at call sites.

- [ ] **Step 5: Run tests (expect PASS)**

```bash
cd backend && pytest tests/unit/test_summary_repository.py -v
```
Expected: all pass (including pre-existing).

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/summary_repository.py backend/tests/unit/test_summary_repository.py
git commit -m "feat(repo): summary_repository.upsert_summary accepts leave_type/remark"
```

---

## Phase C — Backend Services

### Task 6: calculate_status takes leave_type and returns LEAVE

**Files:**
- Modify: `backend/app/services/reporting_service.py`
- Test: extend `backend/tests/unit/test_calculate_status_leave.py`

- [ ] **Step 1: Append failing tests**

```python
"""LEAVE branch tests for calculate_status."""
import datetime

from app.models.daily_attendance_summary import AttendanceStatus
from app.services.reporting_service import calculate_status


SHIFT_START = datetime.time(9, 0)
SHIFT_END = datetime.time(18, 0)


def test_leave_type_set_returns_LEAVE_even_when_late():
    late_clock_in = datetime.datetime(2026, 5, 14, 10, 30)
    status = calculate_status(
        SHIFT_START, SHIFT_END,
        first_clock_in=late_clock_in,
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        leave_type="特休",
    )
    assert status == AttendanceStatus.LEAVE


def test_leave_type_set_with_no_punches_returns_LEAVE_not_None():
    status = calculate_status(
        SHIFT_START, SHIFT_END,
        first_clock_in=None,
        last_clock_out=None,
        leave_type="病假",
    )
    assert status == AttendanceStatus.LEAVE


def test_leave_type_none_preserves_existing_logic():
    on_time = datetime.datetime(2026, 5, 14, 9, 0)
    status = calculate_status(
        SHIFT_START, SHIFT_END,
        first_clock_in=on_time,
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        leave_type=None,
    )
    assert status == AttendanceStatus.NORMAL


def test_empty_leave_type_string_treated_as_none():
    # Defensive: empty string is not a valid leave selection
    late = datetime.datetime(2026, 5, 14, 10, 30)
    status = calculate_status(
        SHIFT_START, SHIFT_END,
        first_clock_in=late,
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        leave_type="",
    )
    assert status == AttendanceStatus.LATE
```

- [ ] **Step 2: Run tests (expect FAIL — unexpected kwarg)**

```bash
cd backend && pytest tests/unit/test_calculate_status_leave.py -v
```

- [ ] **Step 3: Update `calculate_status`**

Replace the function in `backend/app/services/reporting_service.py` (insert `leave_type` as last kwarg; short-circuit at top):

```python
def calculate_status(
    shift_start: datetime.time,
    shift_end: datetime.time,
    first_clock_in: datetime.datetime | None,
    last_clock_out: datetime.datetime | None,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
    leave_type: str | None = None,
) -> AttendanceStatus | None:
    """Determine the attendance status for a single day.

    When ``leave_type`` is a non-empty string, returns ``AttendanceStatus.LEAVE``
    regardless of punch timing.
    """
    if leave_type:  # truthy → non-empty leave type
        return AttendanceStatus.LEAVE

    # ...everything else unchanged
```

Keep the rest of the function body exactly as it was. Treat the empty string as "no leave" via the truthy check (covers the defensive test case).

- [ ] **Step 4: Run tests (expect PASS — both new and existing)**

```bash
cd backend && pytest tests/unit/test_calculate_status_leave.py tests/unit/test_reporting_service.py -v
```
Expected: all pass. (Existing tests don't pass `leave_type`, so they get the default `None` and behavior is unchanged.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reporting_service.py backend/tests/unit/test_calculate_status_leave.py
git commit -m "feat(service): calculate_status returns LEAVE when leave_type provided"
```

---

### Task 7: generate_daily_summary propagates leave_type/remark

**Files:**
- Modify: `backend/app/services/reporting_service.py`
- Test: `backend/tests/unit/test_reporting_service.py` (extend)

- [ ] **Step 1: Append failing tests**

```python
@pytest.mark.asyncio
async def test_generate_daily_summary_preserves_existing_leave_type(db_session):
    # Seed: a summary already exists with leave_type set (e.g. employee pre-filled future day)
    await seed_employee(db_session, emp_id="E020")
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E020",
        date=datetime.date(2026, 5, 14),
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休",
        remark="上午",
    )
    summary = await reporting_service.generate_daily_summary(
        db_session, "E020", datetime.date(2026, 5, 14)
    )
    assert summary.status == AttendanceStatus.LEAVE
    assert summary.leave_type == "特休"
    assert summary.remark == "上午"
```

- [ ] **Step 2: Run test (expect FAIL — existing logic overwrites leave_type)**

```bash
cd backend && pytest tests/unit/test_reporting_service.py::test_generate_daily_summary_preserves_existing_leave_type -v
```

- [ ] **Step 3: Update `generate_daily_summary`**

Modify in `backend/app/services/reporting_service.py`:

```python
async def generate_daily_summary(
    session: AsyncSession,
    emp_id: str,
    date: datetime.date,
) -> DailyAttendanceSummary | None:
    employee = await employee_repository.find_by_id(session, emp_id)
    if employee is None:
        return None

    # Read any existing summary's leave_type/remark so we preserve them
    existing = await summary_repository.find_by_employee(
        session, emp_id, start_date=date, end_date=date
    )
    existing_leave_type = existing[0].leave_type if existing else None
    existing_remark = existing[0].remark if existing else None

    first_log = await attendance_repository.find_first_clock_in(session, emp_id, date)
    last_log = await attendance_repository.find_last_clock_out(session, emp_id, date)

    first_clock_in = first_log.timestamp if first_log is not None else None
    last_clock_out = last_log.timestamp if last_log is not None else None

    grace_minutes = await system_config_repository.get_grace_period(session)
    status = calculate_status(
        employee.shift_start_time,
        employee.shift_end_time,
        first_clock_in,
        last_clock_out,
        grace_minutes=grace_minutes,
        leave_type=existing_leave_type,
    )

    # When no punches AND no leave, return None (existing contract)
    if status is None:
        return None

    summary = await summary_repository.upsert_summary(
        session,
        emp_id=emp_id,
        date=date,
        first_clock_in=first_clock_in,
        last_clock_out=last_clock_out,
        status=status,
        leave_type=existing_leave_type,
        remark=existing_remark,
    )

    return summary
```

- [ ] **Step 4: Update `generate_all_summaries` ABSENT branch to skip employees with leave_type**

In the same file, update the ABSENT loop (after the workday check) to skip employees who already have a `LEAVE` summary for that date. Since the call to `generate_daily_summary` above already returns a `LEAVE` summary when `leave_type` exists, the existing `punched_emp_ids` tracking will naturally cover them — but rename the set semantics. Replace the tracking variable:

```python
    summaries: list[DailyAttendanceSummary] = []
    handled_emp_ids: set[str] = set()  # punched OR on leave

    for emp in employees:
        summary = await generate_daily_summary(session, emp.emp_id, date)
        if summary is not None:
            summaries.append(summary)
            handled_emp_ids.add(emp.emp_id)

    # ...
    for emp in employees:
        if emp.emp_id in handled_emp_ids:
            continue
        # rest unchanged
```

- [ ] **Step 5: Run tests (expect PASS)**

```bash
cd backend && pytest tests/unit/test_reporting_service.py tests/unit/test_calculate_status_leave.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/reporting_service.py backend/tests/unit/test_reporting_service.py
git commit -m "feat(service): generate_daily_summary preserves leave_type/remark; ABSENT skips LEAVE rows"
```

---

### Task 8: monthly_submission_service

**Files:**
- Create: `backend/app/services/monthly_submission_service.py`
- Test: integration via Task 12; for now create a thin service module.

- [ ] **Step 1: Create the service**

`backend/app/services/monthly_submission_service.py`:

```python
"""Monthly submission service — thin layer over monthly_submission_repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monthly_submission import MonthlySubmission
from app.repositories import monthly_submission_repository


async def submit_month(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> MonthlySubmission:
    """Upsert the (emp_id, year, month) row, refreshing submitted_at."""
    return await monthly_submission_repository.upsert(
        session, emp_id=emp_id, year=year, month=month
    )


async def is_submitted(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> bool:
    row = await monthly_submission_repository.find(
        session, emp_id=emp_id, year=year, month=month
    )
    return row is not None


async def get_status(
    session: AsyncSession,
    emp_id: str,
    year: int,
    month: int,
) -> MonthlySubmission | None:
    return await monthly_submission_repository.find(
        session, emp_id=emp_id, year=year, month=month
    )
```

- [ ] **Step 2: Smoke-import**

```bash
cd backend && python -c "from app.services import monthly_submission_service; print(dir(monthly_submission_service))"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/monthly_submission_service.py
git commit -m "feat(service): add monthly_submission_service (submit_month, is_submitted, get_status)"
```

---

### Task 9: Permission service — DELETE_EMPLOYEE constant; HR loses it

**Files:**
- Modify: `backend/app/services/permission_service.py`
- Test: extend `backend/tests/unit/test_permission_service.py` (find it first)

- [ ] **Step 1: Confirm test file path**

```bash
ls backend/tests/unit/ | grep -i permission
```

- [ ] **Step 2: Write failing tests**

Append to the permission test file:

```python
def test_hr_cannot_delete_employee():
    assert has_permission(Role.HR, "delete_employee") is False


def test_admin_can_delete_employee():
    assert has_permission(Role.ADMIN, "delete_employee") is True


def test_manager_cannot_delete_employee():
    assert has_permission(Role.MANAGER, "delete_employee") is False
```

- [ ] **Step 3: Run tests (expect FAIL — permission constant not defined)**

```bash
cd backend && pytest tests/unit/test_permission_service.py -v
```

- [ ] **Step 4: Update permission service**

In `backend/app/services/permission_service.py`, add a new constant and adjust ADMIN's set:

```python
DELETE_EMPLOYEE: str = "delete_employee"

# ...

_ADMIN_PERMISSIONS: frozenset[str] = _HR_PERMISSIONS | frozenset({
    MANAGE_ROLES,
    MANAGE_CONFIG,
    DELETE_EMPLOYEE,
})
```

(HR's set does NOT get `DELETE_EMPLOYEE` — adding only to admin keeps HR locked out.)

- [ ] **Step 5: Run tests (expect PASS)**

```bash
cd backend && pytest tests/unit/test_permission_service.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/permission_service.py backend/tests/unit/test_permission_service.py
git commit -m "feat(perm): introduce DELETE_EMPLOYEE; HR cannot delete, ADMIN can"
```

---

### Task 10: Apply DELETE_EMPLOYEE gate at router

**Files:**
- Modify: `backend/app/routers/employees.py:122-125`
- Test: `backend/tests/integration/test_employees_delete_permission.py`

- [ ] **Step 1: Write failing integration test**

`backend/tests/integration/test_employees_delete_permission.py`:

```python
"""Tests that DELETE /api/employees/{emp_id} is ADMIN-only."""
import pytest
from httpx import AsyncClient

from tests.conftest import login_as  # use whatever helper exists in conftest for getting JWT tokens by role


@pytest.mark.asyncio
async def test_hr_delete_employee_returns_403(client: AsyncClient):
    hr_token = await login_as(client, role="HR")
    response = await client.delete(
        "/api/employees/E999",
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_delete_employee_returns_404_for_missing(client: AsyncClient):
    admin_token = await login_as(client, role="ADMIN")
    response = await client.delete(
        "/api/employees/E_does_not_exist",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # 404 (not 403) proves the permission check passed
    assert response.status_code == 404
```

> If `login_as` doesn't exist, look at how other integration tests in `backend/tests/integration/` obtain auth tokens, and follow that pattern.

- [ ] **Step 2: Run tests (expect FAIL: HR currently gets 404, not 403)**

```bash
cd backend && pytest tests/integration/test_employees_delete_permission.py -v
```

- [ ] **Step 3: Update the router**

In `backend/app/routers/employees.py`, change the dependency on the DELETE handler:

```python
@router.delete("/{emp_id}")
async def delete_employee(
    emp_id: str,
    user: dict = require_role(Role.ADMIN),  # was Role.HR
    session: AsyncSession = Depends(get_db),
) -> dict:
```

- [ ] **Step 4: Run tests (expect PASS)**

```bash
cd backend && pytest tests/integration/test_employees_delete_permission.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/employees.py backend/tests/integration/test_employees_delete_permission.py
git commit -m "feat(api): DELETE /api/employees/{id} is now ADMIN-only (revoke HR)"
```

---

### Task 11: reporting_service.get_daily_report submission_filter

**Files:**
- Modify: `backend/app/services/reporting_service.py`
- Test: extend `backend/tests/unit/test_reporting_service.py`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_get_daily_report_submission_filter_submitted_excludes_unsubmitted(db_session):
    # Seed two employees, one with a submission for May 2026
    await seed_employee(db_session, emp_id="E030")
    await seed_employee(db_session, emp_id="E031")
    await summary_repository.upsert_summary(
        db_session, emp_id="E030", date=datetime.date(2026, 5, 14),
        first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        status=AttendanceStatus.NORMAL,
    )
    await summary_repository.upsert_summary(
        db_session, emp_id="E031", date=datetime.date(2026, 5, 14),
        first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        status=AttendanceStatus.NORMAL,
    )
    await monthly_submission_repository.upsert(db_session, emp_id="E030", year=2026, month=5)

    rows = await reporting_service.get_daily_report(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        submission_filter="submitted",
    )
    ids = [r.emp_id for r in rows]
    assert "E030" in ids
    assert "E031" not in ids


@pytest.mark.asyncio
async def test_get_daily_report_submission_filter_all(db_session):
    # ...same seed as above
    rows = await reporting_service.get_daily_report(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        submission_filter="all",
    )
    ids = [r.emp_id for r in rows]
    assert "E030" in ids
    assert "E031" in ids


@pytest.mark.asyncio
async def test_get_daily_report_submission_filter_unsubmitted_only(db_session):
    # ...same seed
    rows = await reporting_service.get_daily_report(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        submission_filter="unsubmitted",
    )
    ids = [r.emp_id for r in rows]
    assert "E031" in ids
    assert "E030" not in ids
```

- [ ] **Step 2: Run tests (expect FAIL — unexpected kwarg)**

```bash
cd backend && pytest tests/unit/test_reporting_service.py -v -k "submission_filter"
```

- [ ] **Step 3: Update `get_daily_report`**

Modify the signature and add filtering at the bottom of the function:

```python
async def get_daily_report(
    session: AsyncSession,
    start_date: datetime.date,
    end_date: datetime.date | None = None,
    department: str | None = None,
    emp_id: str | None = None,
    status_filter: str | None = None,
    include_terminated: bool = False,
    submission_filter: str = "submitted",  # NEW: "submitted" | "unsubmitted" | "all"
) -> list[DailyAttendanceSummary]:
    # ...existing body unchanged through `if status_filter ...`
    # Then BEFORE the final sort, apply submission filter:
    if submission_filter != "all":
        # Build a map of (year, month) -> submitted_emp_ids set, on demand
        cache: dict[tuple[int, int], set[str]] = {}

        async def _is_submitted(emp: str, d: datetime.date) -> bool:
            key = (d.year, d.month)
            if key not in cache:
                cache[key] = await monthly_submission_repository.submitted_emp_ids(
                    session, year=d.year, month=d.month
                )
            return emp in cache[key]

        filtered: list[DailyAttendanceSummary] = []
        for s in all_summaries:
            submitted = await _is_submitted(s.emp_id, s.date)
            if submission_filter == "submitted" and submitted:
                filtered.append(s)
            elif submission_filter == "unsubmitted" and not submitted:
                filtered.append(s)
        all_summaries = filtered

    all_summaries.sort(key=lambda s: (s.date, s.emp_id))
    return all_summaries
```

Add the import at the top of the file:
```python
from app.repositories import monthly_submission_repository
```

- [ ] **Step 4: Run tests (expect PASS)**

```bash
cd backend && pytest tests/unit/test_reporting_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reporting_service.py backend/tests/unit/test_reporting_service.py
git commit -m "feat(service): get_daily_report accepts submission_filter (submitted/unsubmitted/all)"
```

---

### Task 12: export_attendance — Chinese headers + new columns + submission_filter

**Files:**
- Modify: `backend/app/services/reporting_service.py`
- Create: `backend/tests/integration/test_export_chinese.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Chinese-ized export with new columns + submission filter."""
import csv
import datetime
import io

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_attendance_summary import AttendanceStatus
from app.repositories import (
    monthly_submission_repository,
    summary_repository,
)
from app.services import reporting_service
from tests.conftest import seed_employee


@pytest.mark.asyncio
async def test_csv_export_uses_chinese_headers(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E040", shift_start="09:00", shift_end="18:00")
    await summary_repository.upsert_summary(
        db_session, emp_id="E040", date=datetime.date(2026, 5, 14),
        first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        status=AttendanceStatus.NORMAL,
    )
    await monthly_submission_repository.upsert(db_session, emp_id="E040", year=2026, month=5)

    csv_text = await reporting_service.export_attendance(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        end_date=datetime.date(2026, 5, 14),
        format="csv",
    )
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    assert header == [
        "員工編號", "姓名", "部門", "日期",
        "班別時間", "上班時間", "下班時間",
        "狀態", "備註", "遲到理由", "送單狀態",
    ]


@pytest.mark.asyncio
async def test_csv_export_translates_status_values(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E041", shift_start="09:00", shift_end="18:00")
    await summary_repository.upsert_summary(
        db_session, emp_id="E041", date=datetime.date(2026, 5, 14),
        first_clock_in=None, last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休", remark="上午",
    )
    await monthly_submission_repository.upsert(db_session, emp_id="E041", year=2026, month=5)

    csv_text = await reporting_service.export_attendance(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        end_date=datetime.date(2026, 5, 14),
        format="csv",
    )
    rows = list(csv.reader(io.StringIO(csv_text)))
    data_row = rows[1]
    assert data_row[7] == "請假"      # 狀態
    assert data_row[8] == "特休·上午"  # 備註
    assert data_row[10] == "已送單"    # 送單狀態


@pytest.mark.asyncio
async def test_csv_export_default_excludes_unsubmitted(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E042", shift_start="09:00", shift_end="18:00")
    await summary_repository.upsert_summary(
        db_session, emp_id="E042", date=datetime.date(2026, 5, 14),
        first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        status=AttendanceStatus.NORMAL,
    )
    # NO submission for E042

    csv_text = await reporting_service.export_attendance(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        end_date=datetime.date(2026, 5, 14),
        format="csv",
    )
    assert "E042" not in csv_text


@pytest.mark.asyncio
async def test_json_export_keeps_english(db_session: AsyncSession):
    await seed_employee(db_session, emp_id="E043", shift_start="09:00", shift_end="18:00")
    await summary_repository.upsert_summary(
        db_session, emp_id="E043", date=datetime.date(2026, 5, 14),
        first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        status=AttendanceStatus.NORMAL,
    )
    await monthly_submission_repository.upsert(db_session, emp_id="E043", year=2026, month=5)

    json_text = await reporting_service.export_attendance(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        end_date=datetime.date(2026, 5, 14),
        format="json",
    )
    assert '"emp_id"' in json_text
    assert '"status": "NORMAL"' in json_text
    assert '"shift_time"' in json_text
    assert '"remark"' in json_text
    assert '"submission_status"' in json_text
```

- [ ] **Step 2: Run tests (expect FAIL)**

```bash
cd backend && pytest tests/integration/test_export_chinese.py -v
```

- [ ] **Step 3: Update `export_attendance`**

Replace the function body in `backend/app/services/reporting_service.py`. Key changes:

1. New `submission_filter: str = "submitted"` parameter.
2. Load `attendance_reasons` per (emp_id, date) for the `遲到理由` column.
3. Load submission status per (emp_id, year, month) — reuse the same cache pattern as Task 11.
4. Build two header sets: Chinese for CSV/Excel, English-snake_case for JSON.
5. Translate status enum value → Chinese only for CSV/Excel paths.
6. Compose `備註` = `leave_type + "·" + remark` (skip whichever is None; both None → empty string).

Use this full replacement:

```python
CHINESE_HEADERS = [
    "員工編號", "姓名", "部門", "日期",
    "班別時間", "上班時間", "下班時間",
    "狀態", "備註", "遲到理由", "送單狀態",
]

JSON_KEYS = [
    "emp_id", "name", "department", "date",
    "shift_time", "first_clock_in", "last_clock_out",
    "status", "remark", "reason", "submission_status",
]

STATUS_ZH = {
    "NORMAL": "正常",
    "LATE": "遲到",
    "EARLY_LEAVE": "早退",
    "LATE_AND_EARLY_LEAVE": "遲到且早退",
    "ABNORMAL": "異常",
    "ABSENT": "缺勤",
    "LEAVE": "請假",
}


def _format_shift_time(start: datetime.time, end: datetime.time) -> str:
    return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"


def _format_remark(leave_type: str | None, remark: str | None) -> str:
    if leave_type and remark:
        return f"{leave_type}·{remark}"
    return leave_type or remark or ""


async def export_attendance(
    session: AsyncSession,
    start_date: datetime.date,
    end_date: datetime.date,
    format: str,
    department: str | None = None,
    emp_id: str | None = None,
    include_terminated: bool = False,
    submission_filter: str = "submitted",
) -> str | bytes:
    # --- determine employees (existing logic) ---
    if emp_id is not None:
        emp = await employee_repository.find_by_id(session, emp_id)
        employees = [emp] if emp is not None else []
    elif department is not None:
        employees = await employee_repository.find_by_department(
            session, department, include_terminated=include_terminated
        )
    else:
        employees = await employee_repository.find_all(
            session, skip=0, limit=10000, include_terminated=include_terminated
        )

    emp_map = {emp.emp_id: emp for emp in employees}

    # --- gather summaries ---
    all_summaries: list[DailyAttendanceSummary] = []
    for emp in employees:
        summaries = await summary_repository.find_by_employee(
            session, emp.emp_id, start_date=start_date, end_date=end_date,
        )
        all_summaries.extend(summaries)

    # --- preload reasons by (emp_id, summary.id) ---
    reason_map: dict[int, str] = {}
    if all_summaries:
        summary_ids = [s.id for s in all_summaries if s.id is not None]
        reasons = await reason_repository.find_by_summary_ids(session, summary_ids)
        for r in reasons:
            reason_map[r.summary_id] = r.reason

    # --- submission filter cache ---
    sub_cache: dict[tuple[int, int], set[str]] = {}

    async def _is_submitted(e: str, d: datetime.date) -> bool:
        key = (d.year, d.month)
        if key not in sub_cache:
            sub_cache[key] = await monthly_submission_repository.submitted_emp_ids(
                session, year=d.year, month=d.month
            )
        return e in sub_cache[key]

    if submission_filter != "all":
        filtered = []
        for s in all_summaries:
            sub = await _is_submitted(s.emp_id, s.date)
            if submission_filter == "submitted" and sub:
                filtered.append(s)
            elif submission_filter == "unsubmitted" and not sub:
                filtered.append(s)
        all_summaries = filtered

    all_summaries.sort(key=lambda s: (s.date, s.emp_id))

    # --- build row dicts (English keys; translate at output time) ---
    rows: list[dict[str, str]] = []
    for s in all_summaries:
        emp = emp_map.get(s.emp_id)
        sub = await _is_submitted(s.emp_id, s.date)
        rows.append({
            "emp_id": s.emp_id,
            "name": emp.name if emp else "",
            "department": emp.department if emp else "",
            "date": s.date.isoformat(),
            "shift_time": _format_shift_time(emp.shift_start_time, emp.shift_end_time) if emp else "",
            "first_clock_in": s.first_clock_in.isoformat() if s.first_clock_in else "",
            "last_clock_out": s.last_clock_out.isoformat() if s.last_clock_out else "",
            "status": s.status.value,
            "remark": _format_remark(s.leave_type, s.remark),
            "reason": reason_map.get(s.id or -1, ""),
            "submission_status": "submitted" if sub else "unsubmitted",
        })

    if format == "json":
        return json.dumps(rows, ensure_ascii=False)

    # CSV / Excel: translate to Chinese
    zh_rows: list[list[str]] = []
    for row in rows:
        zh_rows.append([
            row["emp_id"],
            row["name"],
            row["department"],
            row["date"],
            row["shift_time"],
            row["first_clock_in"],
            row["last_clock_out"],
            STATUS_ZH.get(row["status"], row["status"]),
            row["remark"],
            row["reason"],
            "已送單" if row["submission_status"] == "submitted" else "未送單",
        ])

    if format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance Report"

        bold_font = Font(bold=True)
        for col_idx, header in enumerate(CHINESE_HEADERS, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = bold_font

        for row_idx, row_values in enumerate(zh_rows, 2):
            for col_idx, value in enumerate(row_values, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)

        for col_idx, header in enumerate(CHINESE_HEADERS, 1):
            max_len = len(header)
            for row_values in zh_rows:
                max_len = max(max_len, len(str(row_values[col_idx - 1])))
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max_len + 2

        ws.auto_filter.ref = ws.dimensions

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    # Default: CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CHINESE_HEADERS)
    for row_values in zh_rows:
        writer.writerow(row_values)

    return output.getvalue()
```

Imports to add at top:
```python
from app.repositories import monthly_submission_repository, reason_repository
```

- [ ] **Step 4: Implement `reason_repository.find_by_summary_ids` if missing**

Check `backend/app/repositories/reason_repository.py`. If `find_by_summary_ids` is missing, add:

```python
async def find_by_summary_ids(
    session: AsyncSession,
    summary_ids: list[int],
) -> list[AttendanceReason]:
    if not summary_ids:
        return []
    statement = select(AttendanceReason).where(
        AttendanceReason.summary_id.in_(summary_ids)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/integration/test_export_chinese.py tests/unit/test_reporting_service.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/reporting_service.py \
        backend/app/repositories/reason_repository.py \
        backend/tests/integration/test_export_chinese.py
git commit -m "feat(export): Chinese headers/values, shift_time + remark + reason + submission_status columns, submission_filter"
```

---

## Phase D — Backend Routers

### Task 13: monthly_submissions router

**Files:**
- Create: `backend/app/schemas/monthly_submission.py`
- Create: `backend/app/routers/monthly_submissions.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/integration/test_monthly_submissions_api.py`

- [ ] **Step 1: Create schemas**

`backend/app/schemas/monthly_submission.py`:

```python
"""Schemas for monthly submission endpoints."""
import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SubmitMonthRequest(BaseModel):
    emp_id: str
    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)


class SubmissionResponse(BaseModel):
    emp_id: str
    year: int
    month: int
    submitted_at: datetime.datetime


class SubmissionStatusResponse(BaseModel):
    submitted: bool
    submitted_at: Optional[datetime.datetime] = None
```

- [ ] **Step 2: Write failing integration tests**

`backend/tests/integration/test_monthly_submissions_api.py`:

```python
"""Tests for /api/monthly-submissions."""
import pytest
from httpx import AsyncClient

from tests.conftest import login_as


@pytest.mark.asyncio
async def test_employee_submits_own_month(client: AsyncClient):
    token = await login_as(client, role="EMPLOYEE", emp_id="E050")
    res = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E050", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["emp_id"] == "E050"
    assert res.json()["year"] == 2026
    assert res.json()["month"] == 5


@pytest.mark.asyncio
async def test_employee_cannot_submit_other_employee(client: AsyncClient):
    token = await login_as(client, role="EMPLOYEE", emp_id="E050")
    res = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E999", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_hr_can_submit_any_employee(client: AsyncClient):
    hr_token = await login_as(client, role="HR")
    res = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E060", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_resubmit_updates_timestamp(client: AsyncClient):
    token = await login_as(client, role="EMPLOYEE", emp_id="E070")
    r1 = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E070", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    r2 = await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E070", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["submitted_at"] >= r1.json()["submitted_at"]


@pytest.mark.asyncio
async def test_get_status_reflects_submission(client: AsyncClient):
    token = await login_as(client, role="EMPLOYEE", emp_id="E080")
    before = await client.get(
        "/api/monthly-submissions?emp_id=E080&year=2026&month=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert before.json()["submitted"] is False

    await client.post(
        "/api/monthly-submissions",
        json={"emp_id": "E080", "year": 2026, "month": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    after = await client.get(
        "/api/monthly-submissions?emp_id=E080&year=2026&month=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after.json()["submitted"] is True
    assert after.json()["submitted_at"] is not None
```

- [ ] **Step 3: Run (expect FAIL — 404 not found)**

```bash
cd backend && pytest tests/integration/test_monthly_submissions_api.py -v
```

- [ ] **Step 4: Create router**

`backend/app/routers/monthly_submissions.py`:

```python
"""Monthly submission router."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth_middleware import get_current_user
from app.models.employee import Role
from app.schemas.monthly_submission import (
    SubmissionResponse,
    SubmissionStatusResponse,
    SubmitMonthRequest,
)
from app.services import monthly_submission_service
from app.db import get_db

router = APIRouter(prefix="/api/monthly-submissions", tags=["monthly-submissions"])


def _can_act_on(user: dict, target_emp_id: str) -> bool:
    if user["sub"] == target_emp_id:
        return True
    role = Role(user["role"])
    return role in (Role.HR, Role.ADMIN)


@router.post("", response_model=SubmissionResponse)
async def submit_month(
    body: SubmitMonthRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SubmissionResponse:
    if not _can_act_on(user, body.emp_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot submit for another employee")

    row = await monthly_submission_service.submit_month(
        session, emp_id=body.emp_id, year=body.year, month=body.month
    )
    return SubmissionResponse(
        emp_id=row.emp_id, year=row.year, month=row.month, submitted_at=row.submitted_at
    )


@router.get("", response_model=SubmissionStatusResponse)
async def get_status(
    emp_id: str,
    year: int,
    month: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SubmissionStatusResponse:
    if not _can_act_on(user, emp_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view another employee's submission status")

    row = await monthly_submission_service.get_status(
        session, emp_id=emp_id, year=year, month=month
    )
    if row is None:
        return SubmissionStatusResponse(submitted=False)
    return SubmissionStatusResponse(submitted=True, submitted_at=row.submitted_at)
```

- [ ] **Step 5: Register in `main.py`**

Add to `backend/app/main.py`:
```python
from app.routers import monthly_submissions
# ...
app.include_router(monthly_submissions.router)
```

- [ ] **Step 6: Run tests (expect PASS)**

```bash
cd backend && pytest tests/integration/test_monthly_submissions_api.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/monthly_submission.py \
        backend/app/routers/monthly_submissions.py \
        backend/app/main.py \
        backend/tests/integration/test_monthly_submissions_api.py
git commit -m "feat(api): /api/monthly-submissions POST + GET"
```

---

### Task 14: Leave-types router

**Files:**
- Create: `backend/app/schemas/leave_types.py`
- Create: `backend/app/routers/leave_types.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_leave_types_api.py`

- [ ] **Step 1: Schemas**

`backend/app/schemas/leave_types.py`:
```python
from pydantic import BaseModel, Field


class LeaveTypesResponse(BaseModel):
    types: list[str]


class LeaveTypesUpdateRequest(BaseModel):
    types: list[str] = Field(..., min_length=0, max_length=100)
```

- [ ] **Step 2: Failing tests**

`backend/tests/integration/test_leave_types_api.py`:
```python
import pytest
from httpx import AsyncClient

from tests.conftest import login_as


@pytest.mark.asyncio
async def test_get_leave_types_returns_seeded_defaults(client: AsyncClient):
    token = await login_as(client, role="EMPLOYEE")
    res = await client.get(
        "/api/admin/leave-types",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    types = res.json()["types"]
    assert "特休" in types
    assert "公假" in types


@pytest.mark.asyncio
async def test_put_leave_types_requires_hr(client: AsyncClient):
    employee_token = await login_as(client, role="EMPLOYEE")
    res = await client.put(
        "/api/admin/leave-types",
        json={"types": ["X", "Y"]},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_put_leave_types_as_hr_updates(client: AsyncClient):
    hr_token = await login_as(client, role="HR")
    res = await client.put(
        "/api/admin/leave-types",
        json={"types": ["新假別A", "新假別B"]},
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert res.status_code == 200
    assert res.json()["types"] == ["新假別A", "新假別B"]
```

- [ ] **Step 3: Run (expect FAIL)**

```bash
cd backend && pytest tests/integration/test_leave_types_api.py -v
```

- [ ] **Step 4: Implement router + system_config_repository helpers**

Check `backend/app/repositories/system_config_repository.py`. If `get_leave_types` and `set_leave_types` don't exist, add them following the pattern used by `get_grace_period` etc.:

```python
LEAVE_TYPES_KEY = "leave_types"


async def get_leave_types(session: AsyncSession) -> list[str]:
    row = await session.get(SystemConfig, LEAVE_TYPES_KEY)
    if row is None or not row.value:
        return []
    return list(row.value.get("types", []))


async def set_leave_types(session: AsyncSession, types: list[str]) -> list[str]:
    row = await session.get(SystemConfig, LEAVE_TYPES_KEY)
    if row is None:
        row = SystemConfig(key=LEAVE_TYPES_KEY, value={"types": types})
    else:
        row.value = {"types": types}
    session.add(row)
    await session.commit()
    return types
```

Then create the router `backend/app/routers/leave_types.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.middleware.auth_middleware import require_role
from app.models.employee import Role
from app.repositories import system_config_repository
from app.schemas.leave_types import LeaveTypesResponse, LeaveTypesUpdateRequest

router = APIRouter(prefix="/api/admin/leave-types", tags=["admin-leave-types"])


@router.get("", response_model=LeaveTypesResponse)
async def get_leave_types(
    session: AsyncSession = Depends(get_db),
    _user: dict = require_role(Role.EMPLOYEE),
) -> LeaveTypesResponse:
    types = await system_config_repository.get_leave_types(session)
    return LeaveTypesResponse(types=types)


@router.put("", response_model=LeaveTypesResponse)
async def put_leave_types(
    body: LeaveTypesUpdateRequest,
    session: AsyncSession = Depends(get_db),
    _user: dict = require_role(Role.HR),
) -> LeaveTypesResponse:
    types = await system_config_repository.set_leave_types(session, body.types)
    return LeaveTypesResponse(types=types)
```

Register in `main.py`:
```python
from app.routers import leave_types
app.include_router(leave_types.router)
```

- [ ] **Step 5: Run tests (expect PASS)**

```bash
cd backend && pytest tests/integration/test_leave_types_api.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/leave_types.py \
        backend/app/routers/leave_types.py \
        backend/app/repositories/system_config_repository.py \
        backend/app/main.py \
        backend/tests/integration/test_leave_types_api.py
git commit -m "feat(api): /api/admin/leave-types GET (all) + PUT (HR+)"
```

---

### Task 15: bulk_override accepts leave_type/remark

**Files:**
- Modify: `backend/app/schemas/bulk_override.py`
- Modify: `backend/app/services/attendance_service.py`
- Modify: `backend/app/routers/attendance.py` (pass new fields through)
- Test: extend `backend/tests/integration/test_attendance_*.py` (find the bulk override test file)

- [ ] **Step 1: Update schema**

`backend/app/schemas/bulk_override.py`:
```python
class BulkOverrideEntry(BaseModel):
    date: datetime.date
    first_clock_in: Optional[datetime.time] = None
    last_clock_out: Optional[datetime.time] = None
    leave_type: Optional[str] = Field(default=None, max_length=50)
    remark: Optional[str] = Field(default=None, max_length=500)
```

- [ ] **Step 2: Find bulk override test file**

```bash
ls backend/tests/integration/ | grep -i override
```

- [ ] **Step 3: Add failing integration tests**

Append to that file (or create `backend/tests/integration/test_bulk_override_leave.py`):

```python
@pytest.mark.asyncio
async def test_bulk_override_with_leave_type_marks_LEAVE(client: AsyncClient):
    token = await login_as(client, role="EMPLOYEE", emp_id="E100")
    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [
                {"date": "2026-05-14", "leave_type": "特休", "remark": "上午"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    # Fetch the summary
    summary_res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14&emp_id=E100&submission_filter=all",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = summary_res.json()
    row = next(r for r in body if r["emp_id"] == "E100" and r["date"] == "2026-05-14")
    assert row["status"] == "LEAVE"
    assert row["leave_type"] == "特休"
    assert row["remark"] == "上午"


@pytest.mark.asyncio
async def test_bulk_override_remark_only_does_not_change_status(client: AsyncClient):
    token = await login_as(client, role="EMPLOYEE", emp_id="E101")
    # First create a punched day
    await client.post(...)  # adapt to existing punch helper
    res = await client.put(
        "/api/attendance/override-bulk",
        json={
            "year": 2026, "month": 5,
            "entries": [
                {"date": "2026-05-14", "first_clock_in": "09:00", "last_clock_out": "18:00", "remark": "just a note"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    # status should be NORMAL, remark stored
```

- [ ] **Step 4: Update service**

In `backend/app/services/attendance_service.py`'s `bulk_override_punches`, after the punch-log writes, write to summary's `leave_type`/`remark`:

```python
for entry in entries:
    entry_date = entry["date"]
    clock_in_time = entry.get("first_clock_in")
    clock_out_time = entry.get("last_clock_out")
    leave_type = entry.get("leave_type")
    remark = entry.get("remark")

    if (
        clock_in_time is None
        and clock_out_time is None
        and leave_type is None
        and remark is None
    ):
        continue

    if clock_in_time is not None or clock_out_time is not None:
        # ...existing punch override block unchanged
        pass

    # After punches: regenerate summary, then patch remark fields
    # generate_daily_summary will preserve leave_type/remark from existing row,
    # so we upsert them BEFORE regenerating:
    if leave_type is not None or remark is not None:
        existing = await summary_repository.find_by_employee(
            session, emp_id, start_date=entry_date, end_date=entry_date
        )
        current_status = existing[0].status if existing else AttendanceStatus.ABSENT
        current_in = existing[0].first_clock_in if existing else None
        current_out = existing[0].last_clock_out if existing else None
        await summary_repository.upsert_summary(
            session,
            emp_id=emp_id, date=entry_date,
            first_clock_in=current_in,
            last_clock_out=current_out,
            status=current_status,  # placeholder; regenerated below
            leave_type=leave_type,
            remark=remark,
        )

    summary = await reporting_service.generate_daily_summary(session, emp_id, entry_date)
    # ...rest unchanged
```

> Note: the existing `bulk_override_punches` body must remain functional. The key insight is that `generate_daily_summary` now preserves `leave_type`/`remark` from the existing row, so writing them BEFORE the regen makes them stick.

- [ ] **Step 5: Update router**

In `backend/app/routers/attendance.py`'s `bulk_override`, pass through new fields in the comprehension:

```python
entries=[
    {
        "date": entry.date,
        "first_clock_in": entry.first_clock_in,
        "last_clock_out": entry.last_clock_out,
        "leave_type": entry.leave_type,
        "remark": entry.remark,
    }
    for entry in body.entries
],
```

- [ ] **Step 6: Run tests**

```bash
cd backend && pytest tests/integration/test_bulk_override_leave.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/bulk_override.py \
        backend/app/services/attendance_service.py \
        backend/app/routers/attendance.py \
        backend/tests/integration/test_bulk_override_leave.py
git commit -m "feat(api): bulk_override accepts leave_type/remark per entry"
```

---

### Task 16: reports router accepts submission_filter; daily response includes new fields

**Files:**
- Modify: `backend/app/routers/reports.py`
- Test: `backend/tests/integration/test_reports_submission_filter.py`

- [ ] **Step 1: Write failing tests**

```python
"""End-to-end tests for /api/reports/daily and /api/reports/export submission_filter."""
import pytest
from httpx import AsyncClient

from tests.conftest import login_as


@pytest.mark.asyncio
async def test_daily_default_excludes_unsubmitted(client: AsyncClient):
    # ...seed via API or fixtures: two employees, one submitted
    hr_token = await login_as(client, role="HR")
    res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14",
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    ids = [r["emp_id"] for r in res.json()]
    assert "E_submitted" in ids
    assert "E_unsubmitted" not in ids


@pytest.mark.asyncio
async def test_daily_all_includes_both(client: AsyncClient):
    hr_token = await login_as(client, role="HR")
    res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14&submission_filter=all",
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    ids = [r["emp_id"] for r in res.json()]
    assert "E_submitted" in ids
    assert "E_unsubmitted" in ids


@pytest.mark.asyncio
async def test_non_hr_role_cannot_pass_all_filter(client: AsyncClient):
    emp_token = await login_as(client, role="EMPLOYEE", emp_id="E_submitted")
    # Even if employee passes submission_filter=all, they only see their own data;
    # for non-HR roles, the filter must be silently forced to 'submitted'.
    res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14&submission_filter=all",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    # Their own unsubmitted day (if any) should NOT appear
    for r in res.json():
        assert r["submission_status"] == "submitted"
```

- [ ] **Step 2: Run (expect FAIL — submission_filter not yet accepted)**

```bash
cd backend && pytest tests/integration/test_reports_submission_filter.py -v
```

- [ ] **Step 3: Update router**

In `backend/app/routers/reports.py`:

```python
from app.models.employee import Role

# /daily handler
@router.get("/daily")
async def daily(
    start_date: datetime.date,
    end_date: datetime.date | None = None,
    department: str | None = None,
    emp_id: str | None = None,
    status_filter: str | None = None,
    include_terminated: bool = False,
    submission_filter: str = "submitted",
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    # Force submission_filter to 'submitted' for non-HR roles
    if Role(user["role"]) not in (Role.HR, Role.ADMIN):
        submission_filter = "submitted"

    summaries = await reporting_service.get_daily_report(
        session,
        start_date=start_date,
        end_date=end_date,
        department=department,
        emp_id=emp_id,
        status_filter=status_filter,
        include_terminated=include_terminated,
        submission_filter=submission_filter,
    )
    # Build response — include leave_type, remark, submission_status, reason
    submitted_cache: dict[tuple[int,int], set[str]] = {}
    reasons = await reason_repository.find_by_summary_ids(
        session, [s.id for s in summaries if s.id is not None]
    )
    reason_map = {r.summary_id: r.reason for r in reasons}

    response = []
    for s in summaries:
        key = (s.date.year, s.date.month)
        if key not in submitted_cache:
            submitted_cache[key] = await monthly_submission_repository.submitted_emp_ids(
                session, year=s.date.year, month=s.date.month
            )
        response.append({
            "emp_id": s.emp_id,
            "date": s.date.isoformat(),
            "first_clock_in": s.first_clock_in.isoformat() if s.first_clock_in else None,
            "last_clock_out": s.last_clock_out.isoformat() if s.last_clock_out else None,
            "status": s.status.value,
            "leave_type": s.leave_type,
            "remark": s.remark,
            "reason": reason_map.get(s.id or -1),
            "submission_status": "submitted" if s.emp_id in submitted_cache[key] else "unsubmitted",
        })
    return response
```

For `/export`, do the same: read `submission_filter` from query string, downgrade for non-HR, pass into `export_attendance`.

- [ ] **Step 4: Run tests (expect PASS)**

```bash
cd backend && pytest tests/integration/test_reports_submission_filter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/reports.py backend/tests/integration/test_reports_submission_filter.py
git commit -m "feat(api): reports endpoints accept submission_filter; daily response includes leave_type/remark/reason/submission_status"
```

---

## Phase E — Frontend Foundations

### Task 17: i18n keys

**Files:**
- Modify: `frontend/src/messages/en.json`
- Modify: `frontend/src/messages/zh.json`

- [ ] **Step 1: Add keys to both files**

Append the following keys (preserving existing JSON structure and any unfinished work currently in the diff):

**zh.json:**
```json
{
  "status": {
    "leave": "請假"
  },
  "monthlyOverride": {
    "remark": "備註",
    "leaveType": "假別",
    "leaveTypeNone": "— 無 —",
    "submitMonth": "本月送單",
    "warningTitle": "偵測到 {count} 個異常日",
    "warningBody": "下列日期狀態異常，仍要繼續送出嗎？",
    "backToEdit": "返回修改",
    "proceed": "繼續送出"
  },
  "reports": {
    "shiftTime": "班別時間",
    "remark": "備註",
    "submissionStatus": "送單狀態",
    "submitted": "已送單 ✓",
    "unsubmitted": "未送單",
    "filterSubmitted": "已送單",
    "filterUnsubmitted": "未送單",
    "filterAll": "全部"
  },
  "admin": {
    "leaveTypes": "假別管理",
    "leaveTypesAdd": "新增假別",
    "leaveTypesRemove": "移除"
  }
}
```

**en.json:** mirror with English:
```json
{
  "status": {"leave": "Leave"},
  "monthlyOverride": {
    "remark": "Remark",
    "leaveType": "Leave Type",
    "leaveTypeNone": "— None —",
    "submitMonth": "Submit Month",
    "warningTitle": "{count} abnormal day(s) detected",
    "warningBody": "The following dates have abnormal status. Proceed anyway?",
    "backToEdit": "Back to Edit",
    "proceed": "Proceed"
  },
  "reports": {
    "shiftTime": "Shift",
    "remark": "Remark",
    "submissionStatus": "Submission Status",
    "submitted": "Submitted ✓",
    "unsubmitted": "Unsubmitted",
    "filterSubmitted": "Submitted",
    "filterUnsubmitted": "Unsubmitted",
    "filterAll": "All"
  },
  "admin": {
    "leaveTypes": "Leave Types",
    "leaveTypesAdd": "Add Leave Type",
    "leaveTypesRemove": "Remove"
  }
}
```

> If keys already exist under these namespaces, MERGE rather than overwrite. JSON merge tool: read each file with `Read`, then write the merged result with `Write`. Do not blindly overwrite top-level keys — keep all pre-existing translations intact.

- [ ] **Step 2: Smoke check — run any existing locale parsing test**

```bash
cd frontend && npx vitest run --reporter=verbose 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/messages/en.json frontend/src/messages/zh.json
git commit -m "feat(i18n): add keys for leave remarks, monthly submission, and admin leave types"
```

---

### Task 18: API client modules

**Files:**
- Create: `frontend/src/lib/api/monthly-submissions.ts`
- Create: `frontend/src/lib/api/leave-types.ts`

- [ ] **Step 1: monthly-submissions client**

`frontend/src/lib/api/monthly-submissions.ts`:

```typescript
import { apiFetch } from "./client"  // use whatever the existing fetch wrapper is named — check src/lib/api/

export interface MonthlySubmission {
  emp_id: string
  year: number
  month: number
  submitted_at: string
}

export interface SubmissionStatus {
  submitted: boolean
  submitted_at?: string
}

export async function submitMonth(emp_id: string, year: number, month: number): Promise<MonthlySubmission> {
  return apiFetch<MonthlySubmission>("/api/monthly-submissions", {
    method: "POST",
    body: JSON.stringify({ emp_id, year, month }),
  })
}

export async function getSubmissionStatus(emp_id: string, year: number, month: number): Promise<SubmissionStatus> {
  const qs = new URLSearchParams({ emp_id, year: String(year), month: String(month) })
  return apiFetch<SubmissionStatus>(`/api/monthly-submissions?${qs.toString()}`)
}
```

> Check `frontend/src/lib/api/` for the existing fetch helper's exact name and import path before writing this.

- [ ] **Step 2: leave-types client**

`frontend/src/lib/api/leave-types.ts`:

```typescript
import { apiFetch } from "./client"

export interface LeaveTypes {
  types: string[]
}

export async function getLeaveTypes(): Promise<LeaveTypes> {
  return apiFetch<LeaveTypes>("/api/admin/leave-types")
}

export async function setLeaveTypes(types: string[]): Promise<LeaveTypes> {
  return apiFetch<LeaveTypes>("/api/admin/leave-types", {
    method: "PUT",
    body: JSON.stringify({ types }),
  })
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api/monthly-submissions.ts frontend/src/lib/api/leave-types.ts
git commit -m "feat(frontend): add API clients for monthly-submissions and leave-types"
```

---

## Phase F — Frontend Components

### Task 19: RemarkCell component

**Files:**
- Create: `frontend/src/components/monthly-override/RemarkCell.tsx`
- Create: `frontend/tests/unit/RemarkCell.test.tsx`

- [ ] **Step 1: Write failing component test**

```tsx
import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { RemarkCell } from "@/components/monthly-override/RemarkCell"

const LEAVE_TYPES = ["特休", "病假", "事假"]

describe("RemarkCell", () => {
  it("renders dropdown with leave types and None option", () => {
    render(
      <RemarkCell
        leaveTypes={LEAVE_TYPES}
        leaveType={null}
        remark=""
        onChange={() => {}}
      />
    )
    expect(screen.getByText("— 無 —")).toBeInTheDocument()
    LEAVE_TYPES.forEach((t) => expect(screen.getByText(t)).toBeInTheDocument())
  })

  it("calls onChange when leave type selected", () => {
    const onChange = vi.fn()
    render(
      <RemarkCell
        leaveTypes={LEAVE_TYPES}
        leaveType={null}
        remark=""
        onChange={onChange}
      />
    )
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "特休" } })
    expect(onChange).toHaveBeenCalledWith({ leaveType: "特休", remark: "" })
  })

  it("calls onChange when remark text changes", () => {
    const onChange = vi.fn()
    render(
      <RemarkCell
        leaveTypes={LEAVE_TYPES}
        leaveType="特休"
        remark=""
        onChange={onChange}
      />
    )
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "上午" } })
    expect(onChange).toHaveBeenCalledWith({ leaveType: "特休", remark: "上午" })
  })

  it("supports leave type empty + free text only", () => {
    const onChange = vi.fn()
    render(
      <RemarkCell leaveTypes={LEAVE_TYPES} leaveType={null} remark="" onChange={onChange} />
    )
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "個人提醒" } })
    expect(onChange).toHaveBeenCalledWith({ leaveType: null, remark: "個人提醒" })
  })
})
```

- [ ] **Step 2: Run (expect FAIL)**

```bash
cd frontend && npx vitest run tests/unit/RemarkCell.test.tsx
```

- [ ] **Step 3: Implement component**

```tsx
"use client"
import { useTranslations } from "next-intl"

interface Props {
  leaveTypes: string[]
  leaveType: string | null
  remark: string
  onChange: (val: { leaveType: string | null; remark: string }) => void
}

export function RemarkCell({ leaveTypes, leaveType, remark, onChange }: Props) {
  const t = useTranslations("monthlyOverride")
  return (
    <div className="flex gap-2 items-center">
      <select
        className="border rounded px-2 py-1 text-sm"
        value={leaveType ?? ""}
        onChange={(e) =>
          onChange({
            leaveType: e.target.value === "" ? null : e.target.value,
            remark,
          })
        }
      >
        <option value="">{t("leaveTypeNone")}</option>
        {leaveTypes.map((lt) => (
          <option key={lt} value={lt}>
            {lt}
          </option>
        ))}
      </select>
      <input
        type="text"
        maxLength={500}
        className="border rounded px-2 py-1 text-sm flex-1"
        placeholder={t("remark")}
        value={remark}
        onChange={(e) => onChange({ leaveType, remark: e.target.value })}
      />
    </div>
  )
}
```

- [ ] **Step 4: Run tests (expect PASS)**

```bash
cd frontend && npx vitest run tests/unit/RemarkCell.test.tsx
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/monthly-override/RemarkCell.tsx frontend/tests/unit/RemarkCell.test.tsx
git commit -m "feat(frontend): add RemarkCell component (leave-type dropdown + remark input)"
```

---

### Task 20: WarningModal component

**Files:**
- Create: `frontend/src/components/monthly-override/WarningModal.tsx`
- Create: `frontend/tests/unit/WarningModal.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { WarningModal } from "@/components/monthly-override/WarningModal"

describe("WarningModal", () => {
  const anomalies = [
    { date: "2026-05-12", status: "LATE" },
    { date: "2026-05-13", status: "ABSENT" },
  ]

  it("renders count and offending dates", () => {
    render(
      <WarningModal anomalies={anomalies} onCancel={() => {}} onProceed={() => {}} />
    )
    expect(screen.getByText(/2/)).toBeInTheDocument()
    expect(screen.getByText(/05\/12/)).toBeInTheDocument()
    expect(screen.getByText(/05\/13/)).toBeInTheDocument()
  })

  it("calls onCancel when 返回修改 clicked", () => {
    const onCancel = vi.fn()
    render(
      <WarningModal anomalies={anomalies} onCancel={onCancel} onProceed={() => {}} />
    )
    fireEvent.click(screen.getByText("返回修改"))
    expect(onCancel).toHaveBeenCalled()
  })

  it("calls onProceed when 繼續送出 clicked", () => {
    const onProceed = vi.fn()
    render(
      <WarningModal anomalies={anomalies} onCancel={() => {}} onProceed={onProceed} />
    )
    fireEvent.click(screen.getByText("繼續送出"))
    expect(onProceed).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run (FAIL)**

- [ ] **Step 3: Implement**

```tsx
"use client"
import { useTranslations } from "next-intl"

export interface Anomaly {
  date: string  // YYYY-MM-DD
  status: string  // AttendanceStatus enum value
}

interface Props {
  anomalies: Anomaly[]
  onCancel: () => void
  onProceed: () => void
}

export function WarningModal({ anomalies, onCancel, onProceed }: Props) {
  const t = useTranslations("monthlyOverride")
  const tStatus = useTranslations("status")
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h2 className="text-lg font-semibold mb-3">
          {t("warningTitle", { count: anomalies.length })}
        </h2>
        <p className="mb-3">{t("warningBody")}</p>
        <ul className="mb-4 max-h-64 overflow-auto text-sm font-mono">
          {anomalies.map((a) => {
            const [y, m, d] = a.date.split("-")
            return (
              <li key={a.date}>
                {m}/{d} — {tStatus(a.status.toLowerCase() as never)}
              </li>
            )
          })}
        </ul>
        <div className="flex justify-end gap-2">
          <button className="px-4 py-2 border rounded" onClick={onCancel}>
            {t("backToEdit")}
          </button>
          <button
            className="px-4 py-2 bg-orange-500 text-white rounded"
            onClick={onProceed}
          >
            {t("proceed")}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run (PASS)**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/monthly-override/WarningModal.tsx frontend/tests/unit/WarningModal.test.tsx
git commit -m "feat(frontend): add WarningModal for monthly-override anomaly detection"
```

---

## Phase G — Frontend Pages

### Task 21: Monthly-override page integration

**Files:**
- Modify: `frontend/src/app/dashboard/monthly-override/page.tsx`

- [ ] **Step 1: Read current page**

```bash
cat frontend/src/app/dashboard/monthly-override/page.tsx | head -100
```

- [ ] **Step 2: Add state for leave_type/remark per day, fetch leave types, add Submit Month button, wire WarningModal**

Edit the page to:
1. On mount, fetch `getLeaveTypes()` into state.
2. Per-row data shape extends to `{ date, first_clock_in, last_clock_out, leave_type, remark }`.
3. Render `<RemarkCell>` in a new column.
4. Add `本月送單` button next to `儲存全部`.
5. Both buttons call a shared `validateAnomalies(rows)` helper that returns an `Anomaly[]`. If non-empty, render `<WarningModal>` and wait for user choice.
6. On `onProceed`:
   - `儲存全部` → existing save flow (PUT `/api/attendance/override-bulk` now includes `leave_type`/`remark`).
   - `本月送單` → run save flow first, then `submitMonth(emp_id, year, month)`.

The `validateAnomalies` helper (place in `frontend/src/lib/monthly-override-anomalies.ts` for reuse):

```typescript
import type { Anomaly } from "@/components/monthly-override/WarningModal"

const ABNORMAL_STATUSES = new Set([
  "LATE", "EARLY_LEAVE", "LATE_AND_EARLY_LEAVE", "ABNORMAL", "ABSENT",
])

export function detectAnomalies(rows: Array<{ date: string; computedStatus: string | null }>): Anomaly[] {
  return rows
    .filter((r) => r.computedStatus && ABNORMAL_STATUSES.has(r.computedStatus))
    .map((r) => ({ date: r.date, status: r.computedStatus as string }))
}
```

> The page computes `computedStatus` per row using either backend response after save, or client-side estimation. Choose: compute on backend after save and re-fetch — simpler, fewer client-side bugs. Trigger flow:
> 1. User clicks 儲存全部 / 本月送單.
> 2. Save → API returns `BulkOverrideResponse` with `results[].status` per day.
> 3. Detect anomalies from response.
> 4. If anomalies > 0, show modal. If user cancels, do nothing further. If user proceeds, complete the action (本月送單 calls submitMonth).

- [ ] **Step 3: Manual smoke test**

```bash
cd frontend && npm run dev
# Open http://localhost:3000/dashboard/monthly-override, log in as test employee, exercise:
# - dropdown saves leave_type
# - remark text saves
# - 儲存全部 with a late day → modal shows that date, can cancel or proceed
# - 本月送單 → saves + calls submit endpoint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/dashboard/monthly-override/page.tsx \
        frontend/src/lib/monthly-override-anomalies.ts
git commit -m "feat(frontend): monthly-override page with remark column, submit-month button, warning modal"
```

---

### Task 22: Reports page columns + submission filter

**Files:**
- Modify: `frontend/src/app/reports/page.tsx`

- [ ] **Step 1: Read current page**

```bash
cat frontend/src/app/reports/page.tsx | head -100
```

- [ ] **Step 2: Add submission filter dropdown + new table columns**

Changes:
1. Read user role from auth context.
2. State: `submissionFilter: "submitted" | "unsubmitted" | "all"` (default `"submitted"`).
3. If role is HR or ADMIN, render the dropdown. Otherwise, force `"submitted"` and hide it.
4. Pass `submission_filter` query param on every `/api/reports/daily` and `/api/reports/export` call.
5. Add three new columns to the table:
   - `班別時間` — derived from employee shift fields (need backend to include them — alternatively join from employees endpoint or have backend daily response include `shift_time` string already formatted; for simplicity, add `shift_time` to the daily response in Task 16's response shape if missing).
   - `備註` — `${leave_type ? leave_type + (remark ? " · " + remark : "") : remark ?? ""}`.
   - `送單狀態` — show `已送單 ✓` or `未送單` based on `submission_status`.
6. Keep existing `遲到理由` column (`reason` from response).

> If `shift_time` is not in the daily response shape, extend the backend response in Task 16 to include `shift_time` (compute server-side as `f"{employee.shift_start_time.strftime('%H:%M')} - {employee.shift_end_time.strftime('%H:%M')}"`). Mark this back-edit in your task notes; verify Task 12 export tests still pass after.

- [ ] **Step 3: Smoke test in browser**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/reports/page.tsx
git commit -m "feat(frontend): reports page adds shift-time/remark/submission-status columns + submission filter"
```

---

### Task 23: Admin leave-types tab + hide HR delete button

**Files:**
- Create: `frontend/src/components/admin/LeaveTypeManager.tsx`
- Modify: `frontend/src/app/admin/page.tsx` (or wherever admin sections live — find it)

- [ ] **Step 1: Locate admin page**

```bash
ls frontend/src/app/admin/
```

- [ ] **Step 2: Implement LeaveTypeManager**

```tsx
"use client"
import { useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { getLeaveTypes, setLeaveTypes } from "@/lib/api/leave-types"

export function LeaveTypeManager() {
  const t = useTranslations("admin")
  const [types, setTypes] = useState<string[]>([])
  const [newType, setNewType] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getLeaveTypes().then((r) => setTypes(r.types))
  }, [])

  const persist = async (next: string[]) => {
    setSaving(true)
    try {
      const r = await setLeaveTypes(next)
      setTypes(r.types)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold">{t("leaveTypes")}</h3>
      <ul className="space-y-1">
        {types.map((tp, i) => (
          <li key={tp} className="flex items-center gap-2">
            <span className="flex-1">{tp}</span>
            <button
              className="text-red-600 text-sm"
              onClick={() => persist(types.filter((x) => x !== tp))}
              disabled={saving}
            >
              {t("leaveTypesRemove")}
            </button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <input
          className="border rounded px-2 py-1 flex-1"
          value={newType}
          onChange={(e) => setNewType(e.target.value)}
        />
        <button
          className="bg-blue-500 text-white px-3 py-1 rounded"
          onClick={() => {
            if (newType.trim() && !types.includes(newType.trim())) {
              persist([...types, newType.trim()])
              setNewType("")
            }
          }}
          disabled={saving}
        >
          {t("leaveTypesAdd")}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Mount in admin page**

Add a new tab/section that renders `<LeaveTypeManager />` (mirror how `DepartmentManager` is mounted — find that pattern first).

- [ ] **Step 4: Hide delete button for HR**

In the employee list rendering inside admin page (find where the row's action buttons live), gate the delete button by ADMIN role:

```tsx
{userRole === "ADMIN" && (
  <button onClick={() => handleDelete(emp.emp_id)} className="text-red-600">
    刪除
  </button>
)}
```

- [ ] **Step 5: Smoke test in browser**

Log in as HR → 刪除 button gone. Log in as ADMIN → button visible.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/admin/LeaveTypeManager.tsx \
        frontend/src/app/admin/page.tsx
git commit -m "feat(frontend): admin leave-types manager + hide HR delete button (ADMIN-only)"
```

---

## Phase H — End-to-End Test

### Task 24: Playwright E2E

**Files:**
- Create: `frontend/tests/e2e/leave-and-submit.spec.ts`

- [ ] **Step 1: Write the spec**

```typescript
import { test, expect } from "@playwright/test"

test("employee fills leave, sees 請假, submits month, HR sees 已送單", async ({ page, browser }) => {
  // 1. Employee login
  await page.goto("/login")
  await page.fill('[name="emp_id"]', "E_EMPLOYEE_TEST")
  await page.fill('[name="password"]', "TestPass123!")
  await page.click('button[type="submit"]')
  await expect(page).toHaveURL(/dashboard/)

  // 2. Open monthly-override
  await page.goto("/dashboard/monthly-override")

  // 3. On the first workday row, select 特休 in leave-type dropdown
  const firstRow = page.locator("table tbody tr").first()
  await firstRow.locator("select").selectOption("特休")
  await firstRow.locator('input[type="text"]').fill("上午")

  // 4. Click 儲存全部, dismiss modal if shown
  await page.click("text=儲存全部")
  // No warning expected since the day is now LEAVE
  await expect(firstRow.locator("td", { hasText: "請假" })).toBeVisible()

  // 5. Click 本月送單
  await page.click("text=本月送單")
  await expect(page.locator("text=本月已送出")).toBeVisible({ timeout: 5000 })

  // 6. HR session: log in separately and verify
  const hrContext = await browser.newContext()
  const hrPage = await hrContext.newPage()
  await hrPage.goto("/login")
  await hrPage.fill('[name="emp_id"]', "E_HR_TEST")
  await hrPage.fill('[name="password"]', "TestPass123!")
  await hrPage.click('button[type="submit"]')
  await hrPage.goto("/reports")
  await expect(hrPage.locator(`tr:has-text("E_EMPLOYEE_TEST"):has-text("已送單 ✓")`)).toBeVisible()
})
```

> Adjust selectors as needed once UI is final. The fixture users `E_EMPLOYEE_TEST` and `E_HR_TEST` should be seeded by `backend/seed.py` (already there for dev) — verify these exist or add them.

- [ ] **Step 2: Run E2E**

```bash
cd frontend && npx playwright test tests/e2e/leave-and-submit.spec.ts --headed
```

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/leave-and-submit.spec.ts
git commit -m "test(e2e): employee leave + submit-month, HR sees 已送單"
```

---

## Phase I — Documentation & Memory

### Task 25: Update CLAUDE.md + memory + TODO.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `TODO.md`
- Modify: `C:\Users\kenny\.claude\projects\D--MyWorkData-WebApp-Tools-GoGoFresh-AttendanceRecord\memory\MEMORY.md`
- Modify (replace): `C:\Users\kenny\.claude\projects\D--MyWorkData-WebApp-Tools-GoGoFresh-AttendanceRecord\memory\project_hr_delete_permission.md`
- Delete: `C:\Users\kenny\.claude\projects\D--MyWorkData-WebApp-Tools-GoGoFresh-AttendanceRecord\memory\project_leave_submission_brainstorm.md` (work landed)

- [ ] **Step 1: Add CLAUDE.md decision #30**

Append to the numbered list:
```
30. **LEAVE status + monthly-submission flag** — `daily_attendance_summaries.leave_type` non-NULL forces `calculate_status` to return `LEAVE`, overriding any LATE/EARLY_LEAVE detection. `remark` is a separate free-text supplement that does NOT affect status. The `attendance_reasons` table is unchanged and continues to serve "tardiness reason" — UI shows 備註 (summary fields) and 遲到理由 (reasons table) as independent columns. New `monthly_submissions(emp_id, year, month, submitted_at)` table flags employee self-confirmation; reports `submission_filter=submitted|unsubmitted|all` (default `submitted`) drives both `/api/reports/daily` and `/api/reports/export`; non-HR roles are silently downgraded to `submitted`. Submissions are status flags only (no edit locking, resubmit refreshes timestamp). CSV/Excel exports are Chinese-ized (headers and status values); JSON keeps English keys/enum values. Employee delete now ADMIN-only (HR loses `DELETE /api/employees/{id}`) — `DELETE_EMPLOYEE` permission gates it.
```

- [ ] **Step 2: Update TODO.md**

Add a Phase 15 row marked Done:
```
| 15 | Leave Remarks, Monthly Submission, Export Chinese-ization, ADMIN-only Delete | ~25 backend + ~10 frontend + 1 E2E | Done |
```

- [ ] **Step 3: Update memory**

Replace `project_hr_delete_permission.md` content:

```markdown
---
name: project-hr-delete-permission
description: HR cannot delete employees (ADMIN-only via DELETE_EMPLOYEE permission constant). Reversed 2026-05-14 per meeting decision.
metadata:
  type: project
---

# Fact

`DELETE /api/employees/{id}` is gated by `Role.ADMIN`. HR has `MANAGE_EMPLOYEES` (create/edit) but NOT `DELETE_EMPLOYEE`. The 409 LSA-retention guard still applies to ADMIN.

**Why:** Meeting on 2026-05-13 (item #8) reversed the previous design — owners want destructive employee removal restricted to ADMIN. HR uses `POST /api/employees/{id}/terminate` for ordinary off-boarding (soft delete, reversible, LSA-compliant).

**How to apply:** When discussing employee-delete permissions, treat ADMIN-only as the current state. Do not propose adding `DELETE_EMPLOYEE` back to HR's permission set without explicit user request.
```

Delete `project_leave_submission_brainstorm.md` and remove its line from `MEMORY.md`. Update the line for `project_hr_delete_permission.md` in `MEMORY.md` to remove the "PENDING REVERSAL" note.

- [ ] **Step 4: Final commit**

```bash
git add CLAUDE.md TODO.md
git commit -m "docs: record leave-remarks / monthly-submission / ADMIN-only delete feature (decision #30)"
```

(Memory files live outside the repo — Write/Delete those separately.)

---

## Final Verification

### Task 26: End-to-end smoke + coverage check

- [ ] **Step 1: Full backend test run**

```bash
cd backend && pytest --cov=app --cov-report=term-missing
```
Expected: 0 failures, coverage ≥ 80%.

- [ ] **Step 2: Full frontend test run**

```bash
cd frontend && npx vitest run --coverage
```
Expected: 0 failures, coverage ≥ 80%.

- [ ] **Step 3: E2E**

```bash
cd frontend && npx playwright test
```
Expected: all E2E pass.

- [ ] **Step 4: Manual smoke (per spec §7.3 rollout)**

- Log in as EMPLOYEE → /dashboard/monthly-override → fill 特休 + remark → 儲存 → status shows 請假.
- Click 本月送單 → check submission via GET /api/monthly-submissions.
- Log in as HR → /reports → see 送單狀態 column; filter by 已送單 / 未送單 / 全部; export CSV → Chinese headers, 請假 status value, 已送單 row.
- Log in as HR → /admin → 假別管理 tab → add a leave type → returns 200.
- Log in as HR → /admin employee list → 刪除 button absent.
- Log in as ADMIN → /admin employee list → 刪除 button present → DELETE works (or 409 for LSA-protected).

- [ ] **Step 5: Push to BOTH remotes (per memory feedback_dual_remote_push)**

```bash
git push origin main
git push bitbucket main
```

- [ ] **Step 6: Confirm**

Report completion to user with: total commits, test counts, coverage numbers, any remaining manual items.

---

## Coverage Map (spec → tasks)

| Spec section | Tasks |
|---|---|
| §2.1 LEAVE enum | 2 |
| §2.2 leave_type/remark columns | 1, 2, 5 |
| §2.3 attendance_reasons unchanged | (no task — verified by Task 12 reason column join) |
| §2.4 leave_types in system_config | 1 (seed), 14 (CRUD) |
| §2.5 monthly_submissions table | 1, 3, 4 |
| §3.1 calculate_status leave_type | 6 |
| §3.2 ABSENT vs LEAVE precedence | 7 |
| §3.3 monthly_submission_service | 8 |
| §3.4 submission_filter logic | 11 |
| §4.1 New endpoints | 13, 14 |
| §4.2 Modified endpoints | 15, 16, 10 |
| §4.3 Permission service | 9, 10 |
| §5.1 monthly-override UI | 19, 20, 21 |
| §5.2 reports UI | 22 |
| §5.3 admin UI | 23 |
| §5.4 export file format | 12 |
| §5.5 i18n keys | 17 |
| §6.1-6.3 Tests | 2,4,5,6,7,9,10,11,12,13,14,15,16,19,20 |
| §6.4 E2E | 24 |
| §7 Migration | 1 |
| §8 Risks documented | spec section unchanged; risks addressed inline |
| §9 References | n/a |

**Total: 26 tasks** (24 implementation + final verification + memory/docs).
