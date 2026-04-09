"""Unit tests for employee service — TDD Phase 3B."""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Role
from app.repositories.employee_repository import create_employee
from app.schemas.auth import TokenResponse
from app.schemas.employee import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from app.services.employee_service import (
    authenticate,
    create_employee as svc_create_employee,
    get_by_id,
    get_team_members,
    list_employees,
    update_employee as svc_update_employee,
)
from app.utils.password import hash_password, verify_password


def _make_employee(
    emp_id: str = "EMP001",
    name: str = "Alice Chen",
    department: str = "Engineering",
    role: Role = Role.EMPLOYEE,
    plain_password: str = "secret123",
    shift_start: datetime.time = datetime.time(9, 0),
    shift_end: datetime.time = datetime.time(18, 0),
) -> Employee:
    """Create an Employee model instance with a hashed password."""
    return Employee(
        emp_id=emp_id,
        name=name,
        department=department,
        role=role,
        hashed_password=hash_password(plain_password),
        shift_start_time=shift_start,
        shift_end_time=shift_end,
    )


def _make_create_schema(
    emp_id: str = "EMP001",
    name: str = "Alice Chen",
    department: str = "Engineering",
    role: Role = Role.EMPLOYEE,
    password: str = "secret123",
    shift_start: datetime.time = datetime.time(9, 0),
    shift_end: datetime.time = datetime.time(18, 0),
) -> EmployeeCreate:
    """Create an EmployeeCreate schema for service input."""
    return EmployeeCreate(
        emp_id=emp_id,
        name=name,
        department=department,
        role=role,
        password=password,
        shift_start_time=shift_start,
        shift_end_time=shift_end,
    )


# ---- 1. create_employee hashes password ----


async def test_create_employee_hashes_password(db_session: AsyncSession) -> None:
    """Service must hash the plain password before persisting."""
    data = _make_create_schema(password="my_plain_password")

    response = await svc_create_employee(db_session, data)

    # Verify via the repository that the stored password is hashed, not plain
    from app.repositories.employee_repository import find_by_id

    stored = await find_by_id(db_session, data.emp_id)
    assert stored is not None
    assert stored.hashed_password != "my_plain_password"
    assert verify_password("my_plain_password", stored.hashed_password) is True


# ---- 2. create_employee returns EmployeeResponse without password ----


async def test_create_employee_returns_response_without_password(
    db_session: AsyncSession,
) -> None:
    """Service must return EmployeeResponse which excludes the password."""
    data = _make_create_schema()

    response = await svc_create_employee(db_session, data)

    assert isinstance(response, EmployeeResponse)
    assert response.emp_id == data.emp_id
    assert response.name == data.name
    assert not hasattr(response, "hashed_password") or "hashed_password" not in response.model_fields
    assert not hasattr(response, "password") or "password" not in response.model_fields


# ---- 3. create_employee duplicate id raises ----


async def test_create_employee_duplicate_id_raises(
    db_session: AsyncSession,
) -> None:
    """Creating an employee with an existing emp_id must raise ValueError."""
    data = _make_create_schema(emp_id="EMP_DUP")
    await svc_create_employee(db_session, data)

    with pytest.raises(ValueError, match="already exists"):
        await svc_create_employee(db_session, data)


# ---- 4. authenticate valid credentials ----


async def test_authenticate_employee_valid(db_session: AsyncSession) -> None:
    """Valid credentials must return a TokenResponse with a JWT."""
    employee = _make_employee(emp_id="AUTH001", plain_password="correct_pw")
    await create_employee(db_session, employee)

    result = await authenticate(db_session, "AUTH001", "correct_pw")

    assert isinstance(result, TokenResponse)
    assert result.token_type == "bearer"
    assert len(result.access_token) > 0


# ---- 5. authenticate invalid password ----


async def test_authenticate_employee_invalid_password(
    db_session: AsyncSession,
) -> None:
    """Wrong password must raise ValueError."""
    employee = _make_employee(emp_id="AUTH002", plain_password="correct_pw")
    await create_employee(db_session, employee)

    with pytest.raises(ValueError, match="Invalid credentials"):
        await authenticate(db_session, "AUTH002", "wrong_pw")


# ---- 6. authenticate not found ----


async def test_authenticate_employee_not_found(
    db_session: AsyncSession,
) -> None:
    """Non-existent emp_id must raise the same ValueError (no user enumeration)."""
    with pytest.raises(ValueError, match="Invalid credentials"):
        await authenticate(db_session, "GHOST", "any_pw")


# ---- 7. get_employee_by_id ----


async def test_get_employee_by_id(db_session: AsyncSession) -> None:
    """get_by_id must return an EmployeeResponse for an existing employee."""
    employee = _make_employee(emp_id="GET001")
    await create_employee(db_session, employee)

    result = await get_by_id(db_session, "GET001")

    assert result is not None
    assert isinstance(result, EmployeeResponse)
    assert result.emp_id == "GET001"
    assert result.name == "Alice Chen"


# ---- 8. update_employee role requires admin ----


async def test_update_employee_role_requires_admin(
    db_session: AsyncSession,
) -> None:
    """A non-admin attempting to change an employee's role must raise PermissionError."""
    employee = _make_employee(emp_id="UPD001", role=Role.EMPLOYEE)
    await create_employee(db_session, employee)

    update_data = EmployeeUpdate(role=Role.MANAGER)

    # EMPLOYEE trying to change role -> PermissionError
    with pytest.raises(PermissionError):
        await svc_update_employee(
            db_session, "UPD001", update_data, current_role=Role.EMPLOYEE
        )

    # MANAGER trying to change role -> PermissionError
    with pytest.raises(PermissionError):
        await svc_update_employee(
            db_session, "UPD001", update_data, current_role=Role.MANAGER
        )


# ---- 9. list_employees respects permissions ----


async def test_list_employees_respects_permissions(
    db_session: AsyncSession,
) -> None:
    """HR/ADMIN see all employees; MANAGER sees only their department;
    EMPLOYEE sees only themselves."""
    await create_employee(
        db_session,
        _make_employee(emp_id="LST001", department="Engineering", role=Role.EMPLOYEE),
    )
    await create_employee(
        db_session,
        _make_employee(emp_id="LST002", department="Engineering", role=Role.MANAGER),
    )
    await create_employee(
        db_session,
        _make_employee(emp_id="LST003", department="Sales", role=Role.EMPLOYEE),
    )
    await create_employee(
        db_session,
        _make_employee(emp_id="ADM001", department="Admin", role=Role.ADMIN),
    )

    # ADMIN sees all
    admin_list = await list_employees(
        db_session,
        current_role=Role.ADMIN,
        current_emp_id="ADM001",
        current_department="Admin",
    )
    assert len(admin_list) == 4

    # MANAGER sees only their department
    mgr_list = await list_employees(
        db_session,
        current_role=Role.MANAGER,
        current_emp_id="LST002",
        current_department="Engineering",
    )
    assert len(mgr_list) == 2
    assert all(e.department == "Engineering" for e in mgr_list)

    # EMPLOYEE sees only themselves
    emp_list = await list_employees(
        db_session,
        current_role=Role.EMPLOYEE,
        current_emp_id="LST001",
        current_department="Engineering",
    )
    assert len(emp_list) == 1
    assert emp_list[0].emp_id == "LST001"


# ---- 10. get_team_members for manager ----


async def test_get_team_members_for_manager(db_session: AsyncSession) -> None:
    """get_team_members returns non-manager employees in the given department."""
    await create_employee(
        db_session,
        _make_employee(
            emp_id="MGR001",
            department="Engineering",
            role=Role.MANAGER,
        ),
    )
    await create_employee(
        db_session,
        _make_employee(
            emp_id="ENG001",
            department="Engineering",
            role=Role.EMPLOYEE,
        ),
    )
    await create_employee(
        db_session,
        _make_employee(
            emp_id="ENG002",
            department="Engineering",
            role=Role.EMPLOYEE,
        ),
    )
    await create_employee(
        db_session,
        _make_employee(
            emp_id="SAL001",
            department="Sales",
            role=Role.EMPLOYEE,
        ),
    )

    result = await get_team_members(db_session, "Engineering")

    assert len(result) == 2
    emp_ids = {e.emp_id for e in result}
    assert emp_ids == {"ENG001", "ENG002"}
    assert all(isinstance(e, EmployeeResponse) for e in result)
