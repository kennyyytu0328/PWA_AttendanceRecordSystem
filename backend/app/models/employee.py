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

    # Reporting tree (Phase 15B): self-referential FK to the employee's manager.
    # Authority is computed from this edge (a manager's subtree), NOT from the
    # department label. NULL = top of the org chart (e.g. President). ON DELETE
    # SET NULL so hard-deleting a manager orphans reports rather than blocking.
    reports_to: str | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.String,
            sa.ForeignKey("employees.emp_id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    # Org-chart rank label (e.g. MANAGER / AVP / VP / PRESIDENT). Display only —
    # grants no permissions. Values come from the configurable `ranks` list.
    rank: str | None = Field(default=None)

    shift_start_time: datetime.time = Field(
        sa_column=sa.Column(sa.Time, nullable=False)
    )
    shift_end_time: datetime.time = Field(
        sa_column=sa.Column(sa.Time, nullable=False)
    )

    terminated_at: datetime.datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True, index=True),
    )

    password_changed_at: datetime.datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
