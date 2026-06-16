"""Employee schemas for request/response validation."""

import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.employee import Role


class EmployeeCreate(BaseModel):
    """Schema for creating a new employee."""

    emp_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    department: str = Field(..., min_length=1)
    role: Role
    password: str = Field(..., min_length=1)
    shift_start_time: datetime.time
    shift_end_time: datetime.time
    reports_to: Optional[str] = Field(default=None, min_length=1)
    rank: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_shift_times(self):
        if self.shift_end_time <= self.shift_start_time:
            raise ValueError(
                "shift_end_time must be after shift_start_time"
            )
        return self


class EmployeeResponse(BaseModel):
    """Schema for employee responses — excludes sensitive fields."""

    model_config = ConfigDict(from_attributes=True)

    emp_id: str
    name: str
    department: str
    role: Role
    shift_start_time: datetime.time
    shift_end_time: datetime.time
    terminated_at: Optional[datetime.datetime] = None
    reports_to: Optional[str] = None
    rank: Optional[str] = None


class EmployeeUpdate(BaseModel):
    """Schema for updating an employee — all fields optional."""

    name: Optional[str] = Field(default=None, min_length=1)
    department: Optional[str] = Field(default=None, min_length=1)
    role: Optional[Role] = None
    password: Optional[str] = Field(default=None, min_length=1)
    shift_start_time: Optional[datetime.time] = None
    shift_end_time: Optional[datetime.time] = None
    reports_to: Optional[str] = Field(default=None, min_length=1)
    rank: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_shift_times(self):
        if (
            self.shift_start_time is not None
            and self.shift_end_time is not None
            and self.shift_end_time <= self.shift_start_time
        ):
            raise ValueError(
                "shift_end_time must be after shift_start_time"
            )
        return self
