"""Employee router — CRUD operations with role-based access control."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_role
from app.models.employee import Role
from app.schemas.employee import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from app.services import employee_service
from app.services.permission_service import MANAGE_EMPLOYEES, has_permission

router = APIRouter(prefix="/api/employees", tags=["employees"])


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_employee(
    body: EmployeeCreate,
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Create a new employee. Requires HR or higher role.

    Creating an ADMIN account additionally requires the caller to hold
    MANAGE_ROLES (ADMIN) — HR cannot escalate by minting admins.
    """
    current_role = Role(user["role"])
    try:
        return await employee_service.create_employee(session, body, current_role)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except employee_service.InvalidReportsToError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": str(exc)},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.get("", response_model=list[EmployeeResponse])
async def list_employees(
    skip: int = 0,
    limit: int = 100,
    include_terminated: bool = False,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[EmployeeResponse]:
    """List employees filtered by the caller's role permissions.

    ``include_terminated`` is honored for HR/ADMIN only. Managers and
    employees always see active records only.
    """
    current_role = Role(user["role"])
    current_emp_id = user["sub"]

    # Fetch caller's department for MANAGER filtering
    caller = await employee_service.get_by_id(session, current_emp_id)
    current_department = caller.department if caller else None

    return await employee_service.list_employees(
        session,
        current_role=current_role,
        current_emp_id=current_emp_id,
        current_department=current_department,
        skip=skip,
        limit=limit,
        include_terminated=include_terminated,
    )


@router.get("/{emp_id}", response_model=EmployeeResponse)
async def get_employee(
    emp_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Get a single employee by ID."""
    result = await employee_service.get_by_id(session, emp_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{emp_id}' not found",
        )
    return result


@router.put("/{emp_id}", response_model=EmployeeResponse)
async def update_employee(
    emp_id: str,
    body: EmployeeUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Update an employee.

    - HR+ can update any employee's fields (except role changes need ADMIN).
    - EMPLOYEE can update their own profile (name only, no role changes).
    """
    current_role = Role(user["role"])
    current_emp_id = user["sub"]

    # EMPLOYEE can only update their own record
    is_self_update = current_emp_id == emp_id
    if not is_self_update and not has_permission(current_role, MANAGE_EMPLOYEES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update other employees",
        )

    try:
        return await employee_service.update_employee(
            session, emp_id, body, current_role
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except employee_service.InvalidReportsToError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": str(exc)},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.delete("/{emp_id}")
async def delete_employee(
    emp_id: str,
    user: dict = require_role(Role.ADMIN),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Hard-delete an employee. Requires ADMIN role.

    Only permitted when the employee has no attendance records. Use the
    /terminate endpoint for employees with history (required by Taiwan
    labor law — attendance records must be retained).
    """
    from app.repositories import employee_repository

    if user["sub"] == emp_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    has_logs = await employee_repository.has_attendance_logs(session, emp_id)
    if has_logs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Employee has attendance records and cannot be hard-deleted. "
                "Use /terminate to mark the employee as inactive while "
                "preserving attendance history."
            ),
        )

    deleted = await employee_repository.delete_employee(session, emp_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{emp_id}' not found",
        )
    return {"deleted": True}


@router.post("/{emp_id}/terminate", response_model=EmployeeResponse)
async def terminate_employee(
    emp_id: str,
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Mark an employee as terminated (soft-delete, preserves history).

    Blocks further login. Reversible via /reactivate.
    """
    if user["sub"] == emp_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot terminate your own account",
        )
    try:
        return await employee_service.terminate_employee(session, emp_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post("/{emp_id}/reactivate", response_model=EmployeeResponse)
async def reactivate_employee(
    emp_id: str,
    user: dict = require_role(Role.HR),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Clear termination — rehire an employee."""
    try:
        return await employee_service.reactivate_employee(session, emp_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
