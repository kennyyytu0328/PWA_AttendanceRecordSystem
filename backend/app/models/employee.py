"""Employee model with Role enum."""

import datetime
import enum

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Role(str, enum.Enum):
    """Employee role within the organization."""

    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    HR = "HR"
    ADMIN = "ADMIN"


class Employee(SQLModel, table=True):
    """Employee table — stores staff identity and shift configuration."""

    __tablename__ = "employees"

    emp_id: str = Field(primary_key=True)
    name: str
    department: str
    role: Role = Field(sa_column=sa.Column(sa.Enum(Role), nullable=False))
    hashed_password: str

    shift_start_time: datetime.time = Field(
        sa_column=sa.Column(sa.Time, nullable=False)
    )
    shift_end_time: datetime.time = Field(
        sa_column=sa.Column(sa.Time, nullable=False)
    )
