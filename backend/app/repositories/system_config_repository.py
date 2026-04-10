"""System config repository — async data-access functions."""

import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_config import SystemConfig


async def get_by_key(session: AsyncSession, key: str) -> SystemConfig | None:
    """Return a system config entry by primary key, or None if not found."""
    statement = select(SystemConfig).where(SystemConfig.key == key)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_office_location(session: AsyncSession) -> dict[str, Any] | None:
    """Return the value dict for the 'office_location' config key, or None."""
    config = await get_by_key(session, "office_location")
    if config is None:
        return None
    return config.value


async def get_departments(session: AsyncSession) -> list[str]:
    """Return the list of pre-set departments, defaulting to empty list."""
    config = await get_by_key(session, "departments")
    if config is None:
        return []
    value = config.value
    if isinstance(value, dict) and "list" in value:
        return list(value["list"])
    return []


async def get_grace_period(session: AsyncSession) -> int:
    """Return the grace period in minutes from system config, defaulting to 5."""
    config = await get_by_key(session, "grace_period")
    if config is None:
        return 5
    value = config.value
    if isinstance(value, dict) and "minutes" in value:
        return int(value["minutes"])
    return 5


async def set_config(
    session: AsyncSession,
    key: str,
    value: dict[str, Any],
    updated_by: str | None = None,
) -> SystemConfig:
    """Upsert a system config entry.

    If *key* already exists, update its value, updated_by, and updated_at.
    If not, insert a new row.
    """
    existing = await get_by_key(session, key)

    if existing is not None:
        existing.value = value
        existing.updated_by = updated_by
        existing.updated_at = datetime.datetime.now()
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    config = SystemConfig(
        key=key,
        value=value,
        updated_by=updated_by,
        updated_at=datetime.datetime.now(),
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def get_workday_calendar(
    session: AsyncSession, year: int
) -> dict[str, Any] | None:
    """Get cached workday calendar for a year."""
    config = await get_by_key(session, f"workday_calendar_{year}")
    if config is None:
        return None
    return config.value


async def set_workday_calendar(
    session: AsyncSession,
    year: int,
    entries: list[dict[str, Any]],
    updated_by: str,
) -> SystemConfig:
    """Cache workday calendar data for a year."""
    return await set_config(
        session,
        key=f"workday_calendar_{year}",
        value={"entries": entries, "year": year},
        updated_by=updated_by,
    )
