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


class InvalidReportsToError(ValueError):
    """A reports_to assignment is invalid (self-reference, cycle, or the
    target manager does not exist). Mapped to HTTP 400 by the router.

    Carries a stable machine-readable ``code`` so the frontend can localize the
    message instead of displaying the raw English ``detail``.
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


async def _validate_reports_to(
    session: AsyncSession, emp_id: str, reports_to: str
) -> None:
    """Reject self-reference, unknown managers, and cycle-creating edges.

    A cycle would form if *reports_to* is the employee themselves or sits
    inside the employee's own subtree (i.e. already reports up to them).
    """
    if reports_to == emp_id:
        raise InvalidReportsToError(
            "An employee cannot report to themselves", code="reports_to_self"
        )

    manager = await repo.find_by_id(session, reports_to)
    if manager is None:
        raise InvalidReportsToError(
            f"Manager '{reports_to}' not found", code="reports_to_not_found"
        )

    subtree = await repo.get_subtree_emp_ids(session, emp_id)
    if reports_to in subtree:
        raise InvalidReportsToError(
            "reports_to would create a cycle "
            "(the chosen manager is in this employee's subtree)",
            code="reports_to_cycle",
        )


async def create_employee(
    session: AsyncSession, data: EmployeeCreate, current_role: Role
) -> EmployeeResponse:
    """Create a new employee, hashing the password before persistence.

    Raises
    ------
    PermissionError
        If the caller lacks MANAGE_ROLES (i.e. is not ADMIN) but is trying to
        create an ADMIN account. Prevents privilege escalation via a crafted
        API call that bypasses the admin UI (which hides the ADMIN option from
        non-admins). HR may still create EMPLOYEE/MANAGER/HR accounts.
    ValueError
        If an employee with the same emp_id already exists.
    """
    if data.role == Role.ADMIN and not has_permission(current_role, MANAGE_ROLES):
        raise PermissionError(
            "Only roles with MANAGE_ROLES permission can create ADMIN accounts"
        )

    existing = await repo.find_by_id(session, data.emp_id)
    if existing is not None:
        raise ValueError(f"Employee with emp_id '{data.emp_id}' already exists")

    # A brand-new employee has no subtree yet, so only self-reference and an
    # unknown manager are possible here (no cycle through descendants).
    if data.reports_to is not None:
        if data.reports_to == data.emp_id:
            raise InvalidReportsToError(
                "An employee cannot report to themselves", code="reports_to_self"
            )
        if await repo.find_by_id(session, data.reports_to) is None:
            raise InvalidReportsToError(
                f"Manager '{data.reports_to}' not found",
                code="reports_to_not_found",
            )

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

    # Guard the reporting edge only when reports_to is explicitly set to a
    # non-null value. Setting it to None (un-assigning, making the employee
    # top-level) is always safe.
    if "reports_to" in data.model_fields_set and data.reports_to is not None:
        await _validate_reports_to(session, emp_id, data.reports_to)

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


async def change_password(
    session: AsyncSession,
    emp_id: str,
    current: str,
    new: str,
) -> None:
    """Change an employee's password after verifying the current one.

    Same generic "Invalid credentials" error for not-found / wrong-password /
    terminated, matching the ``authenticate`` pattern (CLAUDE.md decision #4).

    Distinct errors for the two policy violations callers can legitimately
    surface to the user (the JWT already proved who they are):
    - new password equal to current password ("must differ")
    - new password equal to the emp_id ("must not equal employee ID")

    The new password's length / digit policy is enforced by the Pydantic
    schema; this function trusts ``new`` to already satisfy it.

    Raises
    ------
    ValueError
        On any of the conditions above.
    """
    employee = await repo.find_by_id(session, emp_id)
    if employee is None:
        raise ValueError("Invalid credentials")
    if not verify_password(current, employee.hashed_password):
        raise ValueError("Invalid credentials")
    if employee.terminated_at is not None:
        raise ValueError("Invalid credentials")

    if new == current:
        raise ValueError("new password must differ from current password")
    if new == emp_id:
        raise ValueError("new password must not equal employee ID")

    await repo.update_employee(
        session,
        emp_id,
        {
            "hashed_password": hash_password(new),
            "password_changed_at": datetime.now(UTC),
        },
    )
