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


async def get_leave_types(session: AsyncSession) -> list[str]:
    """Return the list of configured leave types, defaulting to empty list."""
    config = await get_by_key(session, "leave_types")
    if config is None:
        return []
    value = config.value
    if isinstance(value, dict) and "types" in value:
        return list(value["types"])
    return []


async def set_leave_types(
    session: AsyncSession,
    types: list[str],
    updated_by: str | None = None,
) -> list[str]:
    """Upsert the leave_types config entry. Returns the stored list."""
    await set_config(
        session,
        key="leave_types",
        value={"types": list(types)},
        updated_by=updated_by,
    )
    return list(types)


_DEFAULT_RANKS: list[str] = ["PRESIDENT", "VP", "AVP", "MANAGER"]


async def get_ranks(session: AsyncSession) -> list[str]:
    """Return the configured org-chart ranks (most-senior first).

    Unlike departments/leave_types (which default to empty), ranks default to
    the standard 4-tier ladder so the org scaffolding works out of the box.
    """
    config = await get_by_key(session, "ranks")
    if config is None:
        return list(_DEFAULT_RANKS)
    value = config.value
    if isinstance(value, dict) and "ranks" in value:
        return list(value["ranks"])
    return list(_DEFAULT_RANKS)


async def set_ranks(
    session: AsyncSession,
    ranks: list[str],
    updated_by: str | None = None,
) -> list[str]:
    """Upsert the ranks config entry. Returns the stored list."""
    await set_config(
        session,
        key="ranks",
        value={"ranks": list(ranks)},
        updated_by=updated_by,
    )
    return list(ranks)


async def get_org_scoping_enabled(session: AsyncSession) -> bool:
    """Whether subtree-scoped manager authority is active.

    Defaults to False (current company-wide behavior) so populating an empty
    reporting tree never makes managers see nobody. ADMIN flips it on once the
    tree is in place (Phase 15D/15E consume this flag).
    """
    config = await get_by_key(session, "org_scoping_enabled")
    if config is None:
        return False
    value = config.value
    if isinstance(value, dict) and "enabled" in value:
        return bool(value["enabled"])
    return False


async def set_org_scoping_enabled(
    session: AsyncSession,
    enabled: bool,
    updated_by: str | None = None,
) -> bool:
    """Upsert the org_scoping_enabled flag. Returns the stored value."""
    await set_config(
        session,
        key="org_scoping_enabled",
        value={"enabled": bool(enabled)},
        updated_by=updated_by,
    )
    return bool(enabled)


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
