"""Schemas for monthly submission endpoints."""

import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SubmitMonthRequest(BaseModel):
    emp_id: str
    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)


class SubmissionResponse(BaseModel):
    emp_id: str
    year: int
    month: int
    submitted_at: datetime.datetime


class SubmissionStatusResponse(BaseModel):
    submitted: bool
    submitted_at: Optional[datetime.datetime] = None
