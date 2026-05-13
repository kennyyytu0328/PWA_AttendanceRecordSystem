"""Unit tests for employee_service.change_password."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Role
from app.repositories import employee_repository as repo
from app.services import employee_service
from app.utils.password import hash_password, verify_password


async def _make_employee(
    session: AsyncSession,
    emp_id: str = "EMP100",
    password: str = "oldPass1",
    terminated_at: datetime.datetime | None = None,
) -> Employee:
    employee = Employee(
        emp_id=emp_id,
        name="Test",
        department="X",
        role=Role.EMPLOYEE,
        hashed_password=hash_password(password),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
        terminated_at=terminated_at,
    )
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee


@pytest.mark.asyncio
async def test_change_password_success(db_session: AsyncSession) -> None:
    await _make_employee(db_session)

    await employee_service.change_password(
        db_session, "EMP100", current="oldPass1", new="newPass1"
    )

    updated = await repo.find_by_id(db_session, "EMP100")
    assert updated is not None
    assert not verify_password("oldPass1", updated.hashed_password)
    assert verify_password("newPass1", updated.hashed_password)
    assert updated.password_changed_at is not None


@pytest.mark.asyncio
async def test_change_password_wrong_current(db_session: AsyncSession) -> None:
    await _make_employee(db_session)

    with pytest.raises(ValueError, match="Invalid credentials"):
        await employee_service.change_password(
            db_session, "EMP100", current="WRONG", new="newPass1"
        )


@pytest.mark.asyncio
async def test_change_password_unknown_employee(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="Invalid credentials"):
        await employee_service.change_password(
            db_session, "GHOST", current="oldPass1", new="newPass1"
        )


@pytest.mark.asyncio
async def test_change_password_terminated(db_session: AsyncSession) -> None:
    await _make_employee(
        db_session,
        terminated_at=datetime.datetime.now(datetime.UTC),
    )

    with pytest.raises(ValueError, match="Invalid credentials"):
        await employee_service.change_password(
            db_session, "EMP100", current="oldPass1", new="newPass1"
        )


@pytest.mark.asyncio
async def test_change_password_same_as_current(
    db_session: AsyncSession,
) -> None:
    await _make_employee(db_session)

    with pytest.raises(ValueError, match="must differ"):
        await employee_service.change_password(
            db_session, "EMP100", current="oldPass1", new="oldPass1"
        )


@pytest.mark.asyncio
async def test_change_password_same_as_emp_id(db_session: AsyncSession) -> None:
    await _make_employee(db_session, emp_id="EMP100", password="oldPass1")

    with pytest.raises(ValueError, match="must not equal employee ID"):
        await employee_service.change_password(
            db_session, "EMP100", current="oldPass1", new="EMP100"
        )
