"""Seed the database with test users matching the Human Test Manual."""

import asyncio
import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.config import settings
from app.models.employee import Employee, Role
from app.utils.password import hash_password

SEED_EMPLOYEES = [
    {
        "emp_id": "ADMIN01",
        "name": "Admin User",
        "department": "IT",
        "role": Role.ADMIN,
        "password": "admin123",
        "shift_start_time": datetime.time(9, 0),
        "shift_end_time": datetime.time(18, 0),
    },
    {
        "emp_id": "HR01",
        "name": "HR Manager",
        "department": "HR",
        "role": Role.HR,
        "password": "hr123456",
        "shift_start_time": datetime.time(9, 0),
        "shift_end_time": datetime.time(18, 0),
    },
    {
        "emp_id": "MGR01",
        "name": "Engineering Manager",
        "department": "Engineering",
        "role": Role.MANAGER,
        "password": "mgr12345",
        "shift_start_time": datetime.time(9, 0),
        "shift_end_time": datetime.time(18, 0),
    },
    {
        "emp_id": "EMP01",
        "name": "Alice Engineer",
        "department": "Engineering",
        "role": Role.EMPLOYEE,
        "password": "emp12345",
        "shift_start_time": datetime.time(9, 0),
        "shift_end_time": datetime.time(18, 0),
    },
    {
        "emp_id": "EMP02",
        "name": "Bob Sales",
        "department": "Sales",
        "role": Role.EMPLOYEE,
        "password": "emp12345",
        "shift_start_time": datetime.time(9, 0),
        "shift_end_time": datetime.time(18, 0),
    },
]


async def seed():
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        for data in SEED_EMPLOYEES:
            password = data.pop("password")
            emp = Employee(**data, hashed_password=hash_password(password))
            session.add(emp)
            print(f"  + {emp.emp_id} ({emp.role.value}) — password: {password}")

        await session.commit()

    await engine.dispose()
    print(f"\nSeeded {len(SEED_EMPLOYEES)} employees.")


if __name__ == "__main__":
    print("Seeding database...\n")
    asyncio.run(seed())
