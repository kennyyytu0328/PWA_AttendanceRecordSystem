"""Phase 15E — subtree-scoped authority enforced on the 4 manager endpoints.

Tree (reports_to):
    MGR1 (Sales)            MGR2 (Sales)
      └ EMP1 (Engineering)    └ EMP2 (Sales)

EMP1 sits in MGR1's subtree but a DIFFERENT department — proving authority
follows the reporting tree, not the department label. EMP2/MGR2 are a separate
branch, invisible to MGR1 when scoping is on.
"""

import datetime
from datetime import UTC, timedelta

import pytest
from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.employee import Employee, Role
from app.repositories import (
    monthly_submission_repository,
    system_config_repository,
)
from app.utils.password import hash_password


def _token(emp_id: str, role: Role) -> str:
    payload = {
        "sub": emp_id,
        "role": role.value,
        "exp": datetime.datetime.now(UTC) + timedelta(hours=1),
    }
    return jose_jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


async def _emp(db_session, emp_id, dept, role, reports_to=None):
    db_session.add(
        Employee(
            emp_id=emp_id,
            name=emp_id,
            department=dept,
            role=role,
            reports_to=reports_to,
            hashed_password=hash_password("pw"),
            shift_start_time=datetime.time(9, 0),
            shift_end_time=datetime.time(18, 0),
        )
    )
    await db_session.commit()


async def _punch(db_session, emp_id, when):
    db_session.add(
        AttendanceLog(
            emp_id=emp_id,
            timestamp=when,
            latitude=25.0,
            longitude=121.0,
            accuracy=10.0,
            ip_address="127.0.0.1",
            work_mode=WorkMode.OFFICE,
        )
    )
    await db_session.commit()


async def _build(db_session):
    await _emp(db_session, "MGR1", "Sales", Role.MANAGER)
    await _emp(db_session, "EMP1", "Engineering", Role.EMPLOYEE, reports_to="MGR1")
    await _emp(db_session, "MGR2", "Sales", Role.MANAGER)
    await _emp(db_session, "EMP2", "Sales", Role.EMPLOYEE, reports_to="MGR2")
    await _emp(db_session, "HR1", "Admin", Role.HR)


# --------------------------------------------------------------------------
# /attendance/team — list, filtered to subtree when scoping on
# --------------------------------------------------------------------------
async def test_team_subtree_when_scoping_on(client, db_session):
    await _build(db_session)
    d = datetime.datetime(2026, 3, 18, 9, 0, tzinfo=UTC)
    await _punch(db_session, "EMP1", d)   # subtree, different dept
    await _punch(db_session, "EMP2", d)   # other branch, same dept as MGR1
    await system_config_repository.set_org_scoping_enabled(db_session, True)

    res = await client.get(
        "/api/attendance/team?start_date=2026-03-18&end_date=2026-03-18",
        headers={"Authorization": f"Bearer {_token('MGR1', Role.MANAGER)}"},
    )
    assert res.status_code == 200, res.text
    emp_ids = {row["emp_id"] for row in res.json()}
    assert "EMP1" in emp_ids       # subtree wins over department
    assert "EMP2" not in emp_ids   # other branch hidden


async def test_team_department_behavior_when_scoping_off(client, db_session):
    """Toggle OFF preserves the legacy department-scoped /team behavior."""
    await _build(db_session)
    d = datetime.datetime(2026, 3, 18, 9, 0, tzinfo=UTC)
    await _punch(db_session, "EMP1", d)   # Engineering
    await _punch(db_session, "EMP2", d)   # Sales (MGR1's department)
    # scoping default OFF

    res = await client.get(
        "/api/attendance/team?start_date=2026-03-18&end_date=2026-03-18",
        headers={"Authorization": f"Bearer {_token('MGR1', Role.MANAGER)}"},
    )
    assert res.status_code == 200, res.text
    emp_ids = {row["emp_id"] for row in res.json()}
    assert "EMP2" in emp_ids        # same department as MGR1 (legacy behavior)
    assert "EMP1" not in emp_ids    # different department


# --------------------------------------------------------------------------
# /attendance/override — single target, 403 when out of subtree
# --------------------------------------------------------------------------
async def _override(client, token, target):
    return await client.post(
        "/api/attendance/override",
        json={
            "target_emp_id": target,
            "latitude": 25.0,
            "longitude": 121.0,
            "accuracy": 10.0,
            "work_mode": "OFFICE",
        },
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_override_in_subtree_ok_out_forbidden_when_on(client, db_session):
    await _build(db_session)
    await system_config_repository.set_org_scoping_enabled(db_session, True)
    tok = _token("MGR1", Role.MANAGER)

    assert (await _override(client, tok, "EMP1")).status_code == 200
    assert (await _override(client, tok, "EMP2")).status_code == 403


async def test_override_unrestricted_when_off(client, db_session):
    await _build(db_session)
    # scoping OFF — legacy behavior lets a manager override anyone
    tok = _token("MGR1", Role.MANAGER)
    assert (await _override(client, tok, "EMP2")).status_code == 200


# --------------------------------------------------------------------------
# /reasons — single target, 403 when out of subtree
# --------------------------------------------------------------------------
async def test_reasons_out_of_subtree_forbidden_when_on(client, db_session):
    await _build(db_session)
    await system_config_repository.set_org_scoping_enabled(db_session, True)
    tok = _token("MGR1", Role.MANAGER)

    in_res = await client.get(
        "/api/reasons?emp_id=EMP1",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert in_res.status_code == 200, in_res.text

    out_res = await client.get(
        "/api/reasons?emp_id=EMP2",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert out_res.status_code == 403


# --------------------------------------------------------------------------
# /reports/daily — list, filtered to subtree when scoping on
# --------------------------------------------------------------------------
async def test_reports_daily_subtree_when_on_and_hr_sees_all(client, db_session):
    await _build(db_session)
    d = datetime.date(2026, 3, 18)
    when = datetime.datetime(2026, 3, 18, 9, 0, tzinfo=UTC)
    await _punch(db_session, "EMP1", when)
    await _punch(db_session, "EMP2", when)
    # Submit both months so the default submission_filter shows them.
    for e in ("EMP1", "EMP2"):
        await monthly_submission_repository.upsert(
            db_session, emp_id=e, year=d.year, month=d.month
        )
    await system_config_repository.set_org_scoping_enabled(db_session, True)

    mgr = await client.get(
        "/api/reports/daily?start_date=2026-03-18&end_date=2026-03-18",
        headers={"Authorization": f"Bearer {_token('MGR1', Role.MANAGER)}"},
    )
    assert mgr.status_code == 200, mgr.text
    mgr_ids = {r["emp_id"] for r in mgr.json()}
    assert "EMP1" in mgr_ids
    assert "EMP2" not in mgr_ids

    hr = await client.get(
        "/api/reports/daily?start_date=2026-03-18&end_date=2026-03-18",
        headers={"Authorization": f"Bearer {_token('HR1', Role.HR)}"},
    )
    hr_ids = {r["emp_id"] for r in hr.json()}
    assert {"EMP1", "EMP2"} <= hr_ids   # HR is company-wide
