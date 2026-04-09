"""SystemConfig model for application-wide settings."""

import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class SystemConfig(SQLModel, table=True):
    """System config table — key-value store for application settings."""

    __tablename__ = "system_config"

    key: str = Field(primary_key=True)
    value: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    updated_by: Optional[str] = Field(
        default=None, foreign_key="employees.emp_id"
    )
    updated_at: Optional[datetime.datetime] = Field(default=None)
