"""POST /api/attendance/punch stores late_leave_reason on the day's summary."""
import datetime
from datetime import UTC, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attendance_log import WorkMode
from app.models.employee import Employee, Role
from app.services.geolocation_service import WorkModeResult
from app.utils.password import hash_password


def _make_token(emp_id: str, role: Role | str) -> str:
    """Create a valid JWT token for testing."""
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


# Real office_location system_config seeding is unnecessary here — like
# tests/e2e/test_punch_workflow.py, we mock geolocation_service directly so
# the rest of the punch flow (tardiness, summary generation, persistence)
# runs against the real DB/service stack.
_FAKE_GEO_RESULT = WorkModeResult(
    work_mode=WorkMode.OFFICE,
    distance_km=0.02,
    accuracy=10.0,
    is_low_accuracy=False,
)


@pytest.mark.asyncio
@freeze_time("2026-07-22 18:31:00")  # Wednesday, after 18:00 shift end
async def test_punch_with_late_reason_stamps_summary(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_employee(db_session, "E910")
    token = _make_token("E910", "EMPLOYEE")
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.services.attendance_service.geolocation_service.determine_work_mode",
        new_callable=AsyncMock,
        return_value=_FAKE_GEO_RESULT,
    ):
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
