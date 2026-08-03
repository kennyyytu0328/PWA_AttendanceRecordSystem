"""Excluded seed accounts (HR01/ADMIN by default) never appear in exports."""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role
from app.repositories import summary_repository
from app.services import reporting_service
from app.utils.password import hash_password


async def _seed_employee(
    db_session: AsyncSession,
    emp_id: str,
    role: Role | str = Role.EMPLOYEE,
) -> Employee:
    role_enum = role if isinstance(role, Role) else Role(role)
    emp = Employee(
        emp_id=emp_id,
        name=f"User {emp_id}",
        department="Engineering",
        role=role_enum,
        hashed_password=hash_password("pass1234"),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


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
