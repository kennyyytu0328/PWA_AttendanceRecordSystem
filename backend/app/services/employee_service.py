"""Employee service — business logic for employee management."""

from datetime import UTC, datetime, timedelta

from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
from app.repositories import employee_repository as repo
from app.schemas.auth import TokenResponse
from app.schemas.employee import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from app.services.permission_service import MANAGE_ROLES, has_permission
from app.utils.password import hash_password, verify_password


async def create_employee(
    session: AsyncSession, data: EmployeeCreate
) -> EmployeeResponse:
    """Create a new employee, hashing the password before persistence.

    Raises
    ------
    ValueError
        If an employee with the same emp_id already exists.
    """
    existing = await repo.find_by_id(session, data.emp_id)
    if existing is not None:
        raise ValueError(f"Employee with emp_id '{data.emp_id}' already exists")

    employee = Employee(
        emp_id=data.emp_id,
        name=data.name,
        department=data.department,
        role=data.role,
        hashed_password=hash_password(data.password),
        shift_start_time=data.shift_start_time,
        shift_end_time=data.shift_end_time,
    )

    saved = await repo.create_employee(session, employee)
    return EmployeeResponse.model_validate(saved)


async def authenticate(
    session: AsyncSession, emp_id: str, password: str
) -> TokenResponse:
    """Authenticate an employee and return a JWT token.

    Uses the same error message for both not-found and wrong-password
    to prevent user enumeration.

    Raises
    ------
    ValueError
        If the employee is not found or the password is incorrect.
    """
    employee = await repo.find_by_id(session, emp_id)
    if employee is None:
        raise ValueError("Invalid credentials")

    if not verify_password(password, employee.hashed_password):
        raise ValueError("Invalid credentials")

    if employee.terminated_at is not None:
        # Same generic error — don't leak account state to attackers
        raise ValueError("Invalid credentials")

    now = datetime.now(UTC)
    payload = {
        "sub": employee.emp_id,
        "role": employee.role.value,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(
            minutes=settings.access_token_expire_minutes,
        ),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

    return TokenResponse(access_token=token)


async def get_by_id(
    session: AsyncSession, emp_id: str
) -> EmployeeResponse | None:
    """Return an employee by ID, or None if not found."""
    employee = await repo.find_by_id(session, emp_id)
    if employee is None:
        return None
    return EmployeeResponse.model_validate(employee)


async def update_employee(
    session: AsyncSession,
    emp_id: str,
    data: EmployeeUpdate,
    current_role: Role,
) -> EmployeeResponse:
    """Update an employee's fields.

    Raises
    ------
    PermissionError
        If the caller's role lacks MANAGE_ROLES permission but is
        trying to change the employee's role.
    ValueError
        If the employee does not exist.
    """
    if data.role is not None and not has_permission(current_role, MANAGE_ROLES):
        raise PermissionError(
            "Only roles with MANAGE_ROLES permission can change employee roles"
        )

    update_dict = data.model_dump(exclude_unset=True)

    # Hash the password if it's being updated
    if "password" in update_dict:
        update_dict["hashed_password"] = hash_password(update_dict.pop("password"))

    updated = await repo.update_employee(session, emp_id, update_dict)
    if updated is None:
        raise ValueError(f"Employee with emp_id '{emp_id}' not found")

    return EmployeeResponse.model_validate(updated)


async def list_employees(
    session: AsyncSession,
    current_role: Role,
    current_emp_id: str,
    current_department: str | None = None,
    skip: int = 0,
    limit: int = 100,
    include_terminated: bool = False,
) -> list[EmployeeResponse]:
    """List employees filtered by the caller's permissions.

    - ADMIN / HR: see all employees. Can opt-in to include terminated.
    - MANAGER: see active employees in their own department only.
    - EMPLOYEE: see only themselves (active or not — self-lookup).
    """
    if current_role in (Role.ADMIN, Role.HR):
        employees = await repo.find_all(
            session,
            skip=skip,
            limit=limit,
            include_terminated=include_terminated,
        )
    elif current_role == Role.MANAGER and current_department is not None:
        employees = await repo.find_by_department(session, current_department)
    else:
        # EMPLOYEE — only their own record
        employee = await repo.find_by_id(session, current_emp_id)
        employees = [employee] if employee is not None else []

    return [EmployeeResponse.model_validate(e) for e in employees]


async def terminate_employee(
    session: AsyncSession, emp_id: str
) -> EmployeeResponse:
    """Soft-delete: mark employee as terminated. Preserves attendance history.

    Raises
    ------
    ValueError
        If the employee does not exist.
    """
    employee = await repo.terminate_employee(session, emp_id)
    if employee is None:
        raise ValueError(f"Employee with emp_id '{emp_id}' not found")
    return EmployeeResponse.model_validate(employee)


async def reactivate_employee(
    session: AsyncSession, emp_id: str
) -> EmployeeResponse:
    """Clear termination — rehire an employee.

    Raises
    ------
    ValueError
        If the employee does not exist.
    """
    employee = await repo.reactivate_employee(session, emp_id)
    if employee is None:
        raise ValueError(f"Employee with emp_id '{emp_id}' not found")
    return EmployeeResponse.model_validate(employee)


async def get_team_members(
    session: AsyncSession, manager_department: str
) -> list[EmployeeResponse]:
    """Return non-manager employees in the given department."""
    employees = await repo.find_by_manager_department(session, manager_department)
    return [EmployeeResponse.model_validate(e) for e in employees]
