"""New system_config getters default correctly and honor stored values."""
import pytest

from app.repositories import system_config_repository as cfg


@pytest.mark.asyncio
async def test_late_reason_leave_types_default(db_session):
    assert await cfg.get_late_reason_required_leave_types(db_session) == ["出差"]


@pytest.mark.asyncio
async def test_late_reason_leave_types_stored(db_session):
    await cfg.set_config(db_session, "late_reason_required_leave_types",
                         {"leave_types": ["出差", "公出"]})
    assert await cfg.get_late_reason_required_leave_types(db_session) == ["出差", "公出"]


@pytest.mark.asyncio
async def test_export_excluded_default(db_session):
    assert await cfg.get_export_excluded_emp_ids(db_session) == ["HR01", "ADMIN"]


@pytest.mark.asyncio
async def test_override_lock_default_and_set(db_session):
    assert await cfg.get_monthly_override_locked(db_session) is False
    assert await cfg.set_monthly_override_locked(db_session, True, "HR01") is True
    assert await cfg.get_monthly_override_locked(db_session) is True
