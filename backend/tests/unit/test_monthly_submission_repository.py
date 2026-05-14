"""Unit tests for monthly_submission_repository."""

import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Role
from app.repositories import monthly_submission_repository as repo


async def _create_employee(
    session: AsyncSession, emp_id: str = "EMP001"
) -> Employee:
    """Helper: insert an employee so FK constraints are satisfied."""
    emp = Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    session.add(emp)
    await session.commit()
    return emp


async def test_upsert_creates_new_row(db_session: AsyncSession) -> None:
    await _create_employee(db_session, "E001")

    row = await repo.upsert(db_session, emp_id="E001", year=2026, month=5)

    assert row.emp_id == "E001"
    assert row.year == 2026
    assert row.month == 5
    assert row.submitted_at is not None


async def test_upsert_refreshes_timestamp_on_resubmit(
    db_session: AsyncSession,
) -> None:
    await _create_employee(db_session, "E001")

    first = await repo.upsert(db_session, emp_id="E001", year=2026, month=5)
    first_ts = first.submitted_at

    second = await repo.upsert(db_session, emp_id="E001", year=2026, month=5)

    assert second.id == first.id  # same row
    assert second.submitted_at >= first_ts


async def test_find_returns_none_when_absent(db_session: AsyncSession) -> None:
    await _create_employee(db_session, "E002")

    result = await repo.find(db_session, emp_id="E002", year=2026, month=5)

    assert result is None


async def test_find_returns_row(db_session: AsyncSession) -> None:
    await _create_employee(db_session, "E003")
    await repo.upsert(db_session, emp_id="E003", year=2026, month=5)

    result = await repo.find(db_session, emp_id="E003", year=2026, month=5)

    assert result is not None
    assert result.emp_id == "E003"


async def test_submitted_emp_ids(db_session: AsyncSession) -> None:
    await _create_employee(db_session, "E004")
    await _create_employee(db_session, "E005")

    await repo.upsert(db_session, emp_id="E004", year=2026, month=5)

    submitted_ids = await repo.submitted_emp_ids(db_session, year=2026, month=5)

    assert "E004" in submitted_ids
    assert "E005" not in submitted_ids


async def test_list_by_month_returns_ordered_by_emp_id(
    db_session: AsyncSession,
) -> None:
    await _create_employee(db_session, "E006")
    await _create_employee(db_session, "E007")

    await repo.upsert(db_session, emp_id="E007", year=2026, month=5)
    await repo.upsert(db_session, emp_id="E006", year=2026, month=5)

    rows = await repo.list_by_month(db_session, year=2026, month=5)

    assert [r.emp_id for r in rows] == ["E006", "E007"]
