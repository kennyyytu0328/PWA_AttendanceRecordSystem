"""Unit tests for Phase 15C system_config repository helpers."""

from app.repositories import system_config_repository as repo


async def test_get_ranks_default(db_session):
    """Unconfigured ranks return the default 4-tier ladder."""
    assert await repo.get_ranks(db_session) == [
        "PRESIDENT",
        "VP",
        "AVP",
        "MANAGER",
    ]


async def test_set_and_get_ranks(db_session):
    stored = await repo.set_ranks(
        db_session, ["PRESIDENT", "VP", "MANAGER"], updated_by="ADMIN1"
    )
    assert stored == ["PRESIDENT", "VP", "MANAGER"]
    assert await repo.get_ranks(db_session) == ["PRESIDENT", "VP", "MANAGER"]


async def test_get_org_scoping_default_false(db_session):
    assert await repo.get_org_scoping_enabled(db_session) is False


async def test_set_and_get_org_scoping(db_session):
    assert (
        await repo.set_org_scoping_enabled(
            db_session, True, updated_by="ADMIN1"
        )
        is True
    )
    assert await repo.get_org_scoping_enabled(db_session) is True

    await repo.set_org_scoping_enabled(db_session, False, updated_by="ADMIN1")
    assert await repo.get_org_scoping_enabled(db_session) is False
