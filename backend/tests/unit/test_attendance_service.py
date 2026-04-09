"""Unit tests for AttendanceService — Phase 3E (TDD).

Tests the punch workflow: clock-in/out, work-mode determination,
override by managers, and immutability guarantees.
"""

import datetime
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.employee import Employee, Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_employee(
    emp_id: str = "EMP100",
    name: str = "Test User",
    role: Role = Role.EMPLOYEE,
) -> Employee:
    """Create a minimal Employee instance for FK satisfaction."""
    return Employee(
        emp_id=emp_id,
        name=name,
        department="Engineering",
        role=role,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )


def _make_manager(
    emp_id: str = "MGR001",
    name: str = "Manager User",
) -> Employee:
    """Create a minimal Manager employee."""
    return Employee(
        emp_id=emp_id,
        name=name,
        department="Engineering",
        role=Role.MANAGER,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )


@dataclass(frozen=True)
class _FakeWorkModeResult:
    """Mirrors the real WorkModeResult for mocking."""

    work_mode: WorkMode
    distance_km: float
    accuracy: float
    is_low_accuracy: bool


def _default_geo_result() -> _FakeWorkModeResult:
    """Standard office geolocation result for most tests."""
    return _FakeWorkModeResult(
        work_mode=WorkMode.OFFICE,
        distance_km=0.05,
        accuracy=10.0,
        is_low_accuracy=False,
    )


def _low_accuracy_geo_result() -> _FakeWorkModeResult:
    """Low-accuracy geolocation result."""
    return _FakeWorkModeResult(
        work_mode=WorkMode.WFH,
        distance_km=5.2,
        accuracy=500.0,
        is_low_accuracy=True,
    )


_GEO_PATCH = "app.services.attendance_service.geolocation_service"


# ---------------------------------------------------------------------------
# 1. punch() creates an attendance log with all metadata
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_punch_creates_attendance_log(mock_geo, db_session: AsyncSession):
    """punch() creates a log entry with all metadata fields populated."""
    from app.services.attendance_service import punch

    mock_geo.determine_work_mode = AsyncMock(return_value=_default_geo_result())

    db_session.add(_make_employee())
    await db_session.commit()

    result = await punch(
        db_session,
        emp_id="EMP100",
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="192.168.1.1",
    )

    assert result.log.id is not None
    assert result.log.emp_id == "EMP100"
    assert result.log.latitude == 25.033
    assert result.log.longitude == 121.565
    assert result.log.accuracy == 10.0
    assert result.log.timestamp is not None
    assert result.log.is_overridden is False


# ---------------------------------------------------------------------------
# 2. punch() captures IP address
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_punch_captures_ip_address(mock_geo, db_session: AsyncSession):
    """IP address from the parameter is stored in the log."""
    from app.services.attendance_service import punch

    mock_geo.determine_work_mode = AsyncMock(return_value=_default_geo_result())

    db_session.add(_make_employee())
    await db_session.commit()

    result = await punch(
        db_session,
        emp_id="EMP100",
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="10.0.0.42",
    )

    assert result.log.ip_address == "10.0.0.42"


# ---------------------------------------------------------------------------
# 3. punch() determines work mode via geolocation service
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_punch_determines_work_mode(mock_geo, db_session: AsyncSession):
    """punch() calls geolocation service and sets work_mode correctly."""
    from app.services.attendance_service import punch

    wfh_result = _FakeWorkModeResult(
        work_mode=WorkMode.WFH,
        distance_km=3.5,
        accuracy=15.0,
        is_low_accuracy=False,
    )
    mock_geo.determine_work_mode = AsyncMock(return_value=wfh_result)

    db_session.add(_make_employee())
    await db_session.commit()

    result = await punch(
        db_session,
        emp_id="EMP100",
        latitude=25.100,
        longitude=121.600,
        accuracy=15.0,
        ip_address="192.168.1.1",
    )

    mock_geo.determine_work_mode.assert_awaited_once_with(
        db_session, 25.100, 121.600, 15.0
    )
    assert result.log.work_mode == WorkMode.WFH
    assert result.work_mode == WorkMode.WFH
    assert result.distance_km == 3.5


# ---------------------------------------------------------------------------
# 4. punch() requires a valid employee
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_punch_requires_valid_employee(mock_geo, db_session: AsyncSession):
    """punch() raises ValueError when emp_id does not exist."""
    from app.services.attendance_service import punch

    mock_geo.determine_work_mode = AsyncMock(return_value=_default_geo_result())

    with pytest.raises(ValueError, match="Employee .* not found"):
        await punch(
            db_session,
            emp_id="NONEXISTENT",
            latitude=25.033,
            longitude=121.565,
            accuracy=10.0,
            ip_address="192.168.1.1",
        )


# ---------------------------------------------------------------------------
# 5. punch() stores immutable log (creates, never updates)
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_punch_stores_immutable_log(mock_geo, db_session: AsyncSession):
    """Each punch creates a new log — no existing logs are modified."""
    from sqlmodel import select

    from app.services.attendance_service import punch

    mock_geo.determine_work_mode = AsyncMock(return_value=_default_geo_result())

    db_session.add(_make_employee())
    await db_session.commit()

    result1 = await punch(
        db_session,
        emp_id="EMP100",
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="192.168.1.1",
    )

    result2 = await punch(
        db_session,
        emp_id="EMP100",
        latitude=25.034,
        longitude=121.566,
        accuracy=12.0,
        ip_address="192.168.1.2",
    )

    # Both entries exist with distinct IDs
    assert result1.log.id != result2.log.id

    stmt = select(AttendanceLog).where(AttendanceLog.emp_id == "EMP100")
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# 6. Multiple punches same day — all recorded
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_multiple_punches_same_day(mock_geo, db_session: AsyncSession):
    """Multiple punches on the same day are all recorded with no restriction."""
    from app.services.attendance_service import punch

    mock_geo.determine_work_mode = AsyncMock(return_value=_default_geo_result())

    db_session.add(_make_employee())
    await db_session.commit()

    results = []
    for i in range(4):
        r = await punch(
            db_session,
            emp_id="EMP100",
            latitude=25.033,
            longitude=121.565,
            accuracy=10.0,
            ip_address=f"192.168.1.{i}",
        )
        results.append(r)

    ids = {r.log.id for r in results}
    assert len(ids) == 4, "All 4 punches should have distinct IDs"


# ---------------------------------------------------------------------------
# 7. Low-accuracy geolocation flagged in result
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_punch_with_low_accuracy_flagged(mock_geo, db_session: AsyncSession):
    """Low-accuracy geolocation still works; is_low_accuracy is True in result."""
    from app.services.attendance_service import punch

    mock_geo.determine_work_mode = AsyncMock(return_value=_low_accuracy_geo_result())

    db_session.add(_make_employee())
    await db_session.commit()

    result = await punch(
        db_session,
        emp_id="EMP100",
        latitude=25.033,
        longitude=121.565,
        accuracy=500.0,
        ip_address="192.168.1.1",
    )

    assert result.is_low_accuracy is True
    assert result.log.id is not None  # Still saved successfully


# ---------------------------------------------------------------------------
# 8. get_today_punches returns all punches for employee today
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_get_today_punches_for_employee(mock_geo, db_session: AsyncSession):
    """get_today_punches returns all punches for an employee on today's date."""
    from app.services.attendance_service import get_today_punches, punch

    mock_geo.determine_work_mode = AsyncMock(return_value=_default_geo_result())

    db_session.add(_make_employee())
    await db_session.commit()

    # Create two punches (these use datetime.now(UTC) internally)
    await punch(
        db_session,
        emp_id="EMP100",
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="192.168.1.1",
    )
    await punch(
        db_session,
        emp_id="EMP100",
        latitude=25.034,
        longitude=121.566,
        accuracy=12.0,
        ip_address="192.168.1.2",
    )

    punches = await get_today_punches(db_session, "EMP100")

    assert len(punches) == 2
    assert all(p.emp_id == "EMP100" for p in punches)


# ---------------------------------------------------------------------------
# 9. Manager can create override entry
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_override_attendance_by_manager(mock_geo, db_session: AsyncSession):
    """Manager can create an override entry with is_overridden=True."""
    from app.services.attendance_service import override_attendance

    mock_geo.determine_work_mode = AsyncMock(return_value=_default_geo_result())

    db_session.add(_make_manager(emp_id="MGR001"))
    db_session.add(_make_employee(emp_id="EMP100"))
    await db_session.commit()

    log = await override_attendance(
        db_session,
        manager_emp_id="MGR001",
        target_emp_id="EMP100",
        latitude=25.033,
        longitude=121.565,
        accuracy=10.0,
        ip_address="10.0.0.1",
        work_mode=WorkMode.OFFICE,
    )

    assert log.id is not None
    assert log.emp_id == "EMP100"
    assert log.is_overridden is True
    assert log.work_mode == WorkMode.OFFICE


# ---------------------------------------------------------------------------
# 10. Employee role cannot override — raises PermissionError
# ---------------------------------------------------------------------------
@patch(_GEO_PATCH)
async def test_override_attendance_by_employee_rejected(
    mock_geo, db_session: AsyncSession
):
    """Employee role cannot override attendance; raises PermissionError."""
    from app.services.attendance_service import override_attendance

    mock_geo.determine_work_mode = AsyncMock(return_value=_default_geo_result())

    db_session.add(_make_employee(emp_id="EMP100"))
    db_session.add(_make_employee(emp_id="EMP200", name="Target User"))
    await db_session.commit()

    with pytest.raises(PermissionError, match="not authorized"):
        await override_attendance(
            db_session,
            manager_emp_id="EMP100",
            target_emp_id="EMP200",
            latitude=25.033,
            longitude=121.565,
            accuracy=10.0,
            ip_address="10.0.0.1",
            work_mode=WorkMode.OFFICE,
        )
