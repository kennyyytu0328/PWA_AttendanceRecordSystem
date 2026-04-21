"""Employee repository — async data-access functions."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog
from app.models.employee import Employee, Role


async def create_employee(session: AsyncSession, employee: Employee) -> Employee:
    """Persist a new employee and return the refreshed instance."""
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee


async def find_by_id(session: AsyncSession, emp_id: str) -> Employee | None:
    """Return an employee by primary key, or None if not found."""
    statement = select(Employee).where(Employee.emp_id == emp_id)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def find_all(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    include_terminated: bool = False,
) -> list[Employee]:
    """Return a paginated list of employees.

    By default excludes terminated employees. Pass include_terminated=True
    for HR audit views.
    """
    statement = select(Employee)
    if not include_terminated:
        statement = statement.where(Employee.terminated_at.is_(None))
    statement = statement.offset(skip).limit(limit)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def find_by_department(
    session: AsyncSession,
    department: str,
    include_terminated: bool = False,
) -> list[Employee]:
    """Return employees in the given department (excludes terminated by default)."""
    statement = select(Employee).where(Employee.department == department)
    if not include_terminated:
        statement = statement.where(Employee.terminated_at.is_(None))
    result = await session.execute(statement)
    return list(result.scalars().all())


async def find_by_role(session: AsyncSession, role: Role) -> list[Employee]:
    """Return all employees with the given role (active only)."""
    statement = (
        select(Employee)
        .where(Employee.role == role)
        .where(Employee.terminated_at.is_(None))
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def update_employee(
    session: AsyncSession, emp_id: str, data: dict
) -> Employee | None:
    """Update an employee's fields and return the refreshed instance.

    Returns None when the employee does not exist.
    Fields are applied from *data* without mutating the caller's dict.
    """
    statement = select(Employee).where(Employee.emp_id == emp_id)
    result = await session.execute(statement)
    employee = result.scalar_one_or_none()
    if employee is None:
        return None

    for key, value in data.items():
        setattr(employee, key, value)

    await session.commit()
    await session.refresh(employee)
    return employee


async def delete_employee(session: AsyncSession, emp_id: str) -> bool:
    """Hard-delete an employee by primary key. Returns True if deleted, False otherwise.

    Callers should use has_attendance_logs() first to avoid FK violations
    and destroying legally-required attendance history. Prefer
    terminate_employee() for employees who quit.
    """
    statement = select(Employee).where(Employee.emp_id == emp_id)
    result = await session.execute(statement)
    employee = result.scalar_one_or_none()
    if employee is None:
        return False

    await session.delete(employee)
    await session.commit()
    return True


async def find_terminated_ids(session: AsyncSession) -> set[str]:
    """Return the set of emp_ids for all terminated employees.

    Lightweight alternative to loading full Employee rows just to filter
    by termination status. Used by reporting_service to hide terminated
    employees from the default daily report.
    """
    statement = select(Employee.emp_id).where(Employee.terminated_at.is_not(None))
    result = await session.execute(statement)
    return set(result.scalars().all())


async def has_attendance_logs(session: AsyncSession, emp_id: str) -> bool:
    """Return True if the employee has any attendance_logs rows."""
    statement = (
        select(func.count())
        .select_from(AttendanceLog)
        .where(AttendanceLog.emp_id == emp_id)
    )
    result = await session.execute(statement)
    return (result.scalar_one() or 0) > 0


async def terminate_employee(
    session: AsyncSession, emp_id: str
) -> Employee | None:
    """Mark an employee as terminated (soft-delete). Returns None if not found."""
    statement = select(Employee).where(Employee.emp_id == emp_id)
    result = await session.execute(statement)
    employee = result.scalar_one_or_none()
    if employee is None:
        return None

    employee.terminated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(employee)
    return employee


async def reactivate_employee(
    session: AsyncSession, emp_id: str
) -> Employee | None:
    """Clear terminated_at to rehire an employee. Returns None if not found."""
    statement = select(Employee).where(Employee.emp_id == emp_id)
    result = await session.execute(statement)
    employee = result.scalar_one_or_none()
    if employee is None:
        return None

    employee.terminated_at = None
    await session.commit()
    await session.refresh(employee)
    return employee


async def find_by_manager_department(
    session: AsyncSession,
    department: str,
    include_terminated: bool = False,
) -> list[Employee]:
    """Return non-manager employees in the given department.

    Useful for finding all employees that report to a manager
    within the same department. Excludes terminated by default.
    """
    statement = (
        select(Employee)
        .where(Employee.department == department)
        .where(Employee.role != Role.MANAGER)
    )
    if not include_terminated:
        statement = statement.where(Employee.terminated_at.is_(None))
    result = await session.execute(statement)
    return list(result.scalars().all())
