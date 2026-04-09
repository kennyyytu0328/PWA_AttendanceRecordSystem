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
    """Create a new employee. Requires HR or higher role."""
    try:
        return await employee_service.create_employee(session, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.get("", response_model=list[EmployeeResponse])
async def list_employees(
    skip: int = 0,
    limit: int = 100,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[EmployeeResponse]:
    """List employees filtered by the caller's role permissions."""
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
    """Delete (deactivate) an employee. ADMIN only."""
    from app.repositories import employee_repository

    deleted = await employee_repository.delete_employee(session, emp_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{emp_id}' not found",
        )
    return {"deleted": True}
