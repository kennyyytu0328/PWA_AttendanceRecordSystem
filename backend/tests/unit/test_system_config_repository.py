"""Tests for system config repository — TDD Phase 2D."""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Role
from app.models.system_config import SystemConfig
from app.repositories.system_config_repository import (
    get_by_key,
    get_office_location,
    set_config,
)


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


async def _seed_employee(session: AsyncSession, emp_id: str = "EMP001") -> Employee:
    """Insert an employee into the database and return it."""
    employee = _make_employee(emp_id=emp_id)
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee


# ---- 1. get_by_key ----


async def test_get_config_by_key(db_session: AsyncSession) -> None:
    """Retrieves config value by key."""
    config = SystemConfig(
        key="app_name",
        value={"name": "GoGoFresh Attendance"},
    )
    db_session.add(config)
    await db_session.commit()

    result = await get_by_key(db_session, "app_name")

    assert result is not None
    assert result.key == "app_name"
    assert result.value == {"name": "GoGoFresh Attendance"}


# ---- 2. get_office_location ----


async def test_get_office_location(db_session: AsyncSession) -> None:
    """Retrieves office_location config and returns the JSONB dict."""
    location_data = {
        "latitude": 25.033,
        "longitude": 121.5654,
        "name": "Taipei HQ",
    }
    config = SystemConfig(key="office_location", value=location_data)
    db_session.add(config)
    await db_session.commit()

    result = await get_office_location(db_session)

    assert result is not None
    assert result["latitude"] == 25.033
    assert result["longitude"] == 121.5654
    assert result["name"] == "Taipei HQ"


# ---- 3. set_config (upsert) ----


async def test_set_config(db_session: AsyncSession) -> None:
    """Upserts config: inserts if not exists, updates if exists."""
    # Insert
    result = await set_config(db_session, "theme", {"mode": "dark"})
    assert result.key == "theme"
    assert result.value == {"mode": "dark"}

    # Update — same key, new value
    result = await set_config(db_session, "theme", {"mode": "light"})
    assert result.key == "theme"
    assert result.value == {"mode": "light"}

    # Verify only one row exists for the key
    check = await get_by_key(db_session, "theme")
    assert check is not None
    assert check.value == {"mode": "light"}


# ---- 4. set_config records updater ----


async def test_set_config_records_updater(db_session: AsyncSession) -> None:
    """Verifies updated_by and updated_at are populated after set."""
    await _seed_employee(db_session, "EMP001")

    result = await set_config(
        db_session,
        "notifications",
        {"enabled": True},
        updated_by="EMP001",
    )

    assert result.updated_by == "EMP001"
    assert result.updated_at is not None
    assert isinstance(result.updated_at, datetime.datetime)


# ---- 5. get nonexistent key ----


async def test_get_nonexistent_key(db_session: AsyncSession) -> None:
    """Returns None for key that doesn't exist."""
    result = await get_by_key(db_session, "nonexistent_key")

    assert result is None
