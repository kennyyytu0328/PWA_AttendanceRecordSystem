"""Tests for /api/reports/daily submission_filter and response fields (Task 16)."""

import datetime
from datetime import UTC, timedelta

from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
from app.utils.password import hash_password


def _make_token(emp_id: str, role: Role | str) -> str:
    role_value = role.value if isinstance(role, Role) else role
    payload = {
        "sub": emp_id,
        "role": role_value,
        "exp": datetime.datetime.now(UTC) + timedelta(hours=1),
    }
    return jose_jwt.encode(
        payload, settings.secret_key, algorithm=settings.algorithm
    )


async def _seed_employee(
    db_session: AsyncSession,
    emp_id: str,
    role: Role | str = Role.EMPLOYEE,
    shift_start_time: datetime.time = datetime.time(9, 0),
    shift_end_time: datetime.time = datetime.time(18, 0),
) -> Employee:
    role_enum = role if isinstance(role, Role) else Role(role)
    emp = Employee(
        emp_id=emp_id,
        name=f"User {emp_id}",
        department="Engineering",
        role=role_enum,
        hashed_password=hash_password("pass1234"),
        shift_start_time=shift_start_time,
        shift_end_time=shift_end_time,
    )
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def test_daily_default_excludes_unsubmitted(
    client: AsyncClient, db_session: AsyncSession
):
    """Default submission_filter='submitted' hides employees with no submission."""
    from app.models.daily_attendance_summary import AttendanceStatus
    from app.repositories import monthly_submission_repository, summary_repository

    await _seed_employee(db_session, emp_id="HR_DEFAULT", role=Role.HR)
    await _seed_employee(db_session, emp_id="E_SUB")
    await _seed_employee(db_session, emp_id="E_UNSUB")

    target_date = datetime.date(2026, 5, 14)
    for emp in ("E_SUB", "E_UNSUB"):
        await summary_repository.upsert_summary(
            db_session,
            emp_id=emp,
            date=target_date,
            first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
            last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
            status=AttendanceStatus.NORMAL,
        )
    await monthly_submission_repository.upsert(
        db_session, emp_id="E_SUB", year=2026, month=5
    )

    hr_token = _make_token("HR_DEFAULT", Role.HR)
    res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14",
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert res.status_code == 200, res.text
    ids = [r["emp_id"] for r in res.json()]
    assert "E_SUB" in ids
    assert "E_UNSUB" not in ids


async def test_daily_submission_filter_all_includes_both(
    client: AsyncClient, db_session: AsyncSession
):
    from app.models.daily_attendance_summary import AttendanceStatus
    from app.repositories import monthly_submission_repository, summary_repository

    await _seed_employee(db_session, emp_id="HR_ALL", role=Role.HR)
    await _seed_employee(db_session, emp_id="E_SUB_ALL")
    await _seed_employee(db_session, emp_id="E_UNSUB_ALL")

    target_date = datetime.date(2026, 5, 14)
    for emp in ("E_SUB_ALL", "E_UNSUB_ALL"):
        await summary_repository.upsert_summary(
            db_session,
            emp_id=emp,
            date=target_date,
            first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
            last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
            status=AttendanceStatus.NORMAL,
        )
    await monthly_submission_repository.upsert(
        db_session, emp_id="E_SUB_ALL", year=2026, month=5
    )

    hr_token = _make_token("HR_ALL", Role.HR)
    res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14"
        "&submission_filter=all",
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert res.status_code == 200, res.text
    ids = [r["emp_id"] for r in res.json()]
    assert "E_SUB_ALL" in ids
    assert "E_UNSUB_ALL" in ids


async def test_daily_response_includes_new_fields(
    client: AsyncClient, db_session: AsyncSession
):
    """Each row carries shift_time, leave_type, remark, reason, submission_status."""
    from app.models.daily_attendance_summary import AttendanceStatus
    from app.repositories import monthly_submission_repository, summary_repository

    await _seed_employee(db_session, emp_id="HR_FIELDS", role=Role.HR)
    await _seed_employee(
        db_session,
        emp_id="E_FIELDS",
        shift_start_time=datetime.time(8, 30),
        shift_end_time=datetime.time(17, 30),
    )

    target_date = datetime.date(2026, 5, 14)
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E_FIELDS",
        date=target_date,
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休",
        remark="上午",
    )
    await monthly_submission_repository.upsert(
        db_session, emp_id="E_FIELDS", year=2026, month=5
    )

    hr_token = _make_token("HR_FIELDS", Role.HR)
    res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14"
        "&emp_id=E_FIELDS",
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    row = next(r for r in body if r["emp_id"] == "E_FIELDS")
    assert row["status"] == "LEAVE"
    assert row["leave_type"] == "特休"
    assert row["remark"] == "上午"
    assert row["shift_time"] == "08:30 - 17:30"
    assert row["submission_status"] == "submitted"
    assert "reason" in row


async def test_daily_employee_role_blocked(
    client: AsyncClient, db_session: AsyncSession
):
    """Plain EMPLOYEE cannot reach /api/reports/daily at all (403)."""
    await _seed_employee(db_session, emp_id="EMP_BLOCKED")
    emp_token = _make_token("EMP_BLOCKED", Role.EMPLOYEE)
    res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14"
        "&submission_filter=all",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 403


async def test_daily_manager_can_request_all(
    client: AsyncClient, db_session: AsyncSession
):
    """Managers need 'all' for daily team monitoring on the team page.

    The previous behavior silently forced managers to 'submitted', which
    blanked out the team page for the current month. The reports page
    UI still hides the toggle from managers, but the backend must allow
    the value so the team page can pass it.
    """
    from app.models.daily_attendance_summary import AttendanceStatus
    from app.repositories import monthly_submission_repository, summary_repository

    await _seed_employee(db_session, emp_id="MGR_ALL", role=Role.MANAGER)
    await _seed_employee(db_session, emp_id="E_SUB_MGR")
    await _seed_employee(db_session, emp_id="E_UNSUB_MGR")

    target_date = datetime.date(2026, 5, 14)
    for emp in ("E_SUB_MGR", "E_UNSUB_MGR"):
        await summary_repository.upsert_summary(
            db_session,
            emp_id=emp,
            date=target_date,
            first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
            last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
            status=AttendanceStatus.NORMAL,
        )
    await monthly_submission_repository.upsert(
        db_session, emp_id="E_SUB_MGR", year=2026, month=5
    )

    mgr_token = _make_token("MGR_ALL", Role.MANAGER)
    res = await client.get(
        "/api/reports/daily?start_date=2026-05-14&end_date=2026-05-14"
        "&submission_filter=all",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res.status_code == 200, res.text
    ids = [r["emp_id"] for r in res.json()]
    assert "E_SUB_MGR" in ids
    assert "E_UNSUB_MGR" in ids
