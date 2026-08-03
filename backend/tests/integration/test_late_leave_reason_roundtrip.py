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
