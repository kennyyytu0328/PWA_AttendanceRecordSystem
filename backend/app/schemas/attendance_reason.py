"""Attendance reason schemas for request/response validation."""

import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReasonSubmitRequest(BaseModel):
    """Schema for submitting a late/early-leave reason."""

    summary_id: int
    reason: str = Field(..., min_length=1, max_length=500)


class ReasonResponse(BaseModel):
    """Schema for attendance reason responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    summary_id: int
    emp_id: str
    reason: str
    created_at: datetime.datetime
