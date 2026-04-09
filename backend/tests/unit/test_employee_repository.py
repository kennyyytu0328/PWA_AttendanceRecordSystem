"""Tests for employee repository — TDD Phase 2A."""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Role
from app.repositories.employee_repository import (
    create_employee,
    delete_employee,
    find_all,
    find_by_department,
    find_by_id,
    find_by_manager_department,
    find_by_role,
    update_employee,
)


def _make_employee(
    emp_id: str = "EMP001",
    name: str = "Alice Chen",
    department: str = "Engineering",
    role: Role = Role.EMPLOYEE,
    hashed_password: str = "hashed_pw_placeholder",
    shift_start: datetime.time = datetime.time(9, 0),
    shift_end: datetime.time = datetime.time(18, 0),
) -> Employee:
    """Create an Employee instance for testing."""
    return Employee(
        emp_id=emp_id,
        name=name,
        department=department,
        role=role,
        hashed_password=hashed_password,
        shift_start_time=shift_start,
        shift_end_time=shift_end,
    )


# ---- 1. create_employee ----


async def test_create_employee(db_session: AsyncSession) -> None:
    employee = _make_employee()

    result = await create_employee(db_session, employee)

    assert result.emp_id == "EMP001"
    assert result.name == "Alice Chen"
    assert result.department == "Engineering"
    assert result.role == Role.EMPLOYEE
    assert result.shift_start_time == datetime.time(9, 0)
    assert result.shift_end_time == datetime.time(18, 0)


# ---- 2. find_by_id (exists) ----


async def test_find_employee_by_id(db_session: AsyncSession) -> None:
    employee = _make_employee()
    await create_employee(db_session, employee)

    result = await find_by_id(db_session, "EMP001")

    assert result is not None
    assert result.emp_id == "EMP001"
    assert result.name == "Alice Chen"


# ---- 3. find_by_id (not found) ----


async def test_find_employee_by_id_not_found(db_session: AsyncSession) -> None:
    result = await find_by_id(db_session, "NONEXISTENT")

    assert result is None


# ---- 4. find_all ----


async def test_find_all_employees(db_session: AsyncSession) -> None:
    await create_employee(db_session, _make_employee(emp_id="EMP001", name="Alice"))
    await create_employee(db_session, _make_employee(emp_id="EMP002", name="Bob"))
    await create_employee(db_session, _make_employee(emp_id="EMP003", name="Charlie"))

    result = await find_all(db_session)

    assert len(result) == 3
    emp_ids = {e.emp_id for e in result}
    assert emp_ids == {"EMP001", "EMP002", "EMP003"}


# ---- 4b. find_all with pagination ----


async def test_find_all_employees_pagination(db_session: AsyncSession) -> None:
    for i in range(1, 6):
        await create_employee(
            db_session,
            _make_employee(emp_id=f"EMP{i:03d}", name=f"Employee {i}"),
        )

    # First page
    page_one = await find_all(db_session, skip=0, limit=2)
    assert len(page_one) == 2

    # Second page
    page_two = await find_all(db_session, skip=2, limit=2)
    assert len(page_two) == 2

    # Third page (only 1 remaining)
    page_three = await find_all(db_session, skip=4, limit=2)
    assert len(page_three) == 1

    # All page IDs must be distinct (no overlap)
    all_ids = {e.emp_id for e in page_one + page_two + page_three}
    assert len(all_ids) == 5


# ---- 5. find_by_department ----


async def test_find_employees_by_department(db_session: AsyncSession) -> None:
    await create_employee(
        db_session,
        _make_employee(emp_id="EMP001", department="Engineering"),
    )
    await create_employee(
        db_session,
        _make_employee(emp_id="EMP002", department="Engineering"),
    )
    await create_employee(
        db_session,
        _make_employee(emp_id="EMP003", department="Sales"),
    )

    result = await find_by_department(db_session, "Engineering")

    assert len(result) == 2
    assert all(e.department == "Engineering" for e in result)


# ---- 6. find_by_role ----


async def test_find_employees_by_role(db_session: AsyncSession) -> None:
    await create_employee(
        db_session,
        _make_employee(emp_id="EMP001", role=Role.EMPLOYEE),
    )
    await create_employee(
        db_session,
        _make_employee(emp_id="EMP002", role=Role.MANAGER),
    )
    await create_employee(
        db_session,
        _make_employee(emp_id="EMP003", role=Role.EMPLOYEE),
    )

    result = await find_by_role(db_session, Role.EMPLOYEE)

    assert len(result) == 2
    assert all(e.role == Role.EMPLOYEE for e in result)


# ---- 7. update_employee ----


async def test_update_employee(db_session: AsyncSession) -> None:
    await create_employee(db_session, _make_employee(emp_id="EMP001", name="Alice"))

    result = await update_employee(
        db_session,
        "EMP001",
        {"name": "Alice Updated", "department": "Sales"},
    )

    assert result is not None
    assert result.name == "Alice Updated"
    assert result.department == "Sales"
    # emp_id must remain unchanged
    assert result.emp_id == "EMP001"


# ---- 8. update_employee (not found) ----


async def test_update_employee_not_found(db_session: AsyncSession) -> None:
    result = await update_employee(
        db_session,
        "NONEXISTENT",
        {"name": "Ghost"},
    )

    assert result is None


# ---- 9. delete_employee ----


async def test_delete_employee(db_session: AsyncSession) -> None:
    await create_employee(db_session, _make_employee(emp_id="EMP001"))

    deleted = await delete_employee(db_session, "EMP001")

    assert deleted is True

    # Verify the employee is gone
    lookup = await find_by_id(db_session, "EMP001")
    assert lookup is None


# ---- 10. find_by_manager_department ----


async def test_find_employees_by_manager(db_session: AsyncSession) -> None:
    """Find all employees in the same department as a manager."""
    await create_employee(
        db_session,
        _make_employee(
            emp_id="MGR001",
            name="Manager Kim",
            department="Engineering",
            role=Role.MANAGER,
        ),
    )
    await create_employee(
        db_session,
        _make_employee(
            emp_id="EMP001",
            name="Alice",
            department="Engineering",
            role=Role.EMPLOYEE,
        ),
    )
    await create_employee(
        db_session,
        _make_employee(
            emp_id="EMP002",
            name="Bob",
            department="Engineering",
            role=Role.EMPLOYEE,
        ),
    )
    await create_employee(
        db_session,
        _make_employee(
            emp_id="EMP003",
            name="Charlie",
            department="Sales",
            role=Role.EMPLOYEE,
        ),
    )

    result = await find_by_manager_department(db_session, "Engineering")

    # Should return only non-manager employees in the department
    assert len(result) == 2
    emp_ids = {e.emp_id for e in result}
    assert emp_ids == {"EMP001", "EMP002"}
    assert all(e.role != Role.MANAGER for e in result)
