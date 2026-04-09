"""Employee repository — async data-access functions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    session: AsyncSession, skip: int = 0, limit: int = 100
) -> list[Employee]:
    """Return a paginated list of all employees."""
    statement = select(Employee).offset(skip).limit(limit)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def find_by_department(
    session: AsyncSession, department: str
) -> list[Employee]:
    """Return all employees belonging to the given department."""
    statement = select(Employee).where(Employee.department == department)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def find_by_role(session: AsyncSession, role: Role) -> list[Employee]:
    """Return all employees with the given role."""
    statement = select(Employee).where(Employee.role == role)
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
    """Delete an employee by primary key. Returns True if deleted, False otherwise."""
    statement = select(Employee).where(Employee.emp_id == emp_id)
    result = await session.execute(statement)
    employee = result.scalar_one_or_none()
    if employee is None:
        return False

    await session.delete(employee)
    await session.commit()
    return True


async def find_by_manager_department(
    session: AsyncSession, department: str
) -> list[Employee]:
    """Return non-manager employees in the given department.

    Useful for finding all employees that report to a manager
    within the same department.
    """
    statement = (
        select(Employee)
        .where(Employee.department == department)
        .where(Employee.role != Role.MANAGER)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())
