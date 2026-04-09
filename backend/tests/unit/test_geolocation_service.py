"""Tests for geolocation service — TDD Phase 3D."""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import WorkMode
from app.models.employee import Employee, Role
from app.models.system_config import SystemConfig
from app.repositories.system_config_repository import get_office_location, set_config
from app.services.geolocation_service import WorkModeResult, determine_work_mode

# Reference office location for all tests
OFFICE_LAT: float = 25.033
OFFICE_LON: float = 121.565

# Pre-computed latitude offsets from OFFICE_LAT (verified via haversine)
# Threshold is 2km (_OFFICE_RADIUS_KM = 2.0)
# 0.00045 degrees north -> ~50m
_OFFSET_50M: float = 0.000_45
# 0.000892 degrees north -> ~99.19m
_OFFSET_99M: float = 0.000_892
# 0.0009 degrees north -> ~100.08m
_OFFSET_100M: float = 0.000_9
# 0.0018 degrees north -> ~200m (within 2km -> OFFICE)
_OFFSET_200M: float = 0.001_8
# 0.0179 degrees north -> ~1.99km (just within 2km threshold)
_OFFSET_2KM: float = 0.0179
# 0.028 degrees north -> ~3.1km (outside 2km -> WFH)
_OFFSET_3KM: float = 0.028


def _make_employee(
    emp_id: str = "EMP001",
    name: str = "Admin User",
    department: str = "IT",
    role: Role = Role.ADMIN,
    hashed_password: str = "hashed_pw_placeholder",
    shift_start: datetime.time = datetime.time(9, 0),
    shift_end: datetime.time = datetime.time(18, 0),
) -> Employee:
    """Create an Employee instance for FK satisfaction."""
    return Employee(
        emp_id=emp_id,
        name=name,
        department=department,
        role=role,
        hashed_password=hashed_password,
        shift_start_time=shift_start,
        shift_end_time=shift_end,
    )


async def _seed_office_location(session: AsyncSession) -> None:
    """Insert an employee (for FK) and office_location config."""
    employee = _make_employee()
    session.add(employee)
    await session.commit()

    await set_config(
        session,
        "office_location",
        {"latitude": OFFICE_LAT, "longitude": OFFICE_LON, "name": "Taipei HQ"},
        updated_by="EMP001",
    )


# ---- 1. In office (50m away) ----


async def test_determine_work_mode_office(db_session: AsyncSession) -> None:
    """Point ~50m from office should return OFFICE work mode."""
    await _seed_office_location(db_session)

    result = await determine_work_mode(
        db_session,
        latitude=OFFICE_LAT + _OFFSET_50M,
        longitude=OFFICE_LON,
        accuracy=10.0,
    )

    assert result.work_mode == WorkMode.OFFICE
    assert result.distance_km < 0.1


# ---- 2. WFH (3km away — beyond 2km threshold) ----


async def test_determine_work_mode_wfh(db_session: AsyncSession) -> None:
    """Point ~3km from office should return WFH work mode."""
    await _seed_office_location(db_session)

    result = await determine_work_mode(
        db_session,
        latitude=OFFICE_LAT + _OFFSET_3KM,
        longitude=OFFICE_LON,
        accuracy=10.0,
    )

    assert result.work_mode == WorkMode.WFH
    assert result.distance_km >= 2.0


# ---- 3. Within 2km -> OFFICE ----


async def test_determine_work_mode_200m_is_office(db_session: AsyncSession) -> None:
    """Point ~200m from office (within 2km threshold) should return OFFICE."""
    await _seed_office_location(db_session)

    result = await determine_work_mode(
        db_session,
        latitude=OFFICE_LAT + _OFFSET_200M,
        longitude=OFFICE_LON,
        accuracy=10.0,
    )

    assert result.work_mode == WorkMode.OFFICE
    assert result.distance_km < 2.0


# ---- 4. Boundary: ~2km -> OFFICE (within threshold) ----


async def test_determine_work_mode_boundary_2km(db_session: AsyncSession) -> None:
    """Point ~2km from office (at boundary) should return OFFICE."""
    await _seed_office_location(db_session)

    result = await determine_work_mode(
        db_session,
        latitude=OFFICE_LAT + _OFFSET_2KM,
        longitude=OFFICE_LON,
        accuracy=10.0,
    )

    assert result.work_mode == WorkMode.OFFICE
    assert result.distance_km <= 2.0


# ---- 5. Reads office location from config (not hardcoded) ----


async def test_reads_office_location_from_config(db_session: AsyncSession) -> None:
    """Verify service reads location from system_config, not hardcoded values."""
    employee = _make_employee()
    db_session.add(employee)
    await db_session.commit()

    # Set a DIFFERENT office location (far from default)
    custom_lat = 35.6762
    custom_lon = 139.6503
    await set_config(
        db_session,
        "office_location",
        {"latitude": custom_lat, "longitude": custom_lon, "name": "Tokyo Office"},
        updated_by="EMP001",
    )

    # Clock in right at the custom location -> should be OFFICE
    result = await determine_work_mode(
        db_session,
        latitude=custom_lat,
        longitude=custom_lon,
        accuracy=10.0,
    )

    assert result.work_mode == WorkMode.OFFICE
    assert result.distance_km < 0.001  # essentially 0


# ---- 6. Office location not configured -> ValueError ----


async def test_office_location_not_configured(db_session: AsyncSession) -> None:
    """Raises ValueError when office_location config is missing."""
    with pytest.raises(ValueError, match="Office location not configured"):
        await determine_work_mode(
            db_session,
            latitude=OFFICE_LAT,
            longitude=OFFICE_LON,
            accuracy=10.0,
        )


# ---- 7. Accuracy threshold -> is_low_accuracy ----


async def test_validates_accuracy_threshold(db_session: AsyncSession) -> None:
    """Accuracy > 500m should set is_low_accuracy=True."""
    await _seed_office_location(db_session)

    # High accuracy (good GPS) -> is_low_accuracy=False
    result_good = await determine_work_mode(
        db_session,
        latitude=OFFICE_LAT,
        longitude=OFFICE_LON,
        accuracy=50.0,
    )
    assert result_good.is_low_accuracy is False

    # Low accuracy (bad GPS) -> is_low_accuracy=True
    result_bad = await determine_work_mode(
        db_session,
        latitude=OFFICE_LAT,
        longitude=OFFICE_LON,
        accuracy=501.0,
    )
    assert result_bad.is_low_accuracy is True

    # Boundary: exactly 500 -> is_low_accuracy=False
    result_boundary = await determine_work_mode(
        db_session,
        latitude=OFFICE_LAT,
        longitude=OFFICE_LON,
        accuracy=500.0,
    )
    assert result_boundary.is_low_accuracy is False


# ---- 8. Result captures all metadata ----


async def test_captures_metadata(db_session: AsyncSession) -> None:
    """WorkModeResult contains work_mode, distance_km, accuracy, is_low_accuracy."""
    await _seed_office_location(db_session)

    result = await determine_work_mode(
        db_session,
        latitude=OFFICE_LAT + _OFFSET_50M,
        longitude=OFFICE_LON,
        accuracy=25.0,
    )

    assert isinstance(result, WorkModeResult)
    assert result.work_mode in (WorkMode.OFFICE, WorkMode.WFH)
    assert isinstance(result.distance_km, float)
    assert result.distance_km >= 0.0
    assert result.accuracy == 25.0
    assert isinstance(result.is_low_accuracy, bool)
