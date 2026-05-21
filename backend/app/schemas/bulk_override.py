"""Schemas for bulk punch override."""

from __future__ import annotations

import datetime
import decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BulkOverrideEntry(BaseModel):
    """A single day's override data."""

    date: datetime.date
    first_clock_in: Optional[datetime.time] = None
    last_clock_out: Optional[datetime.time] = None
    leave_type: Optional[str] = Field(default=None, max_length=50)
    remark: Optional[str] = Field(default=None, max_length=500)
    overtime_hours: Optional[decimal.Decimal] = Field(default=None)

    @field_validator("overtime_hours")
    @classmethod
    def _validate_overtime_step(
        cls, v: Optional[decimal.Decimal]
    ) -> Optional[decimal.Decimal]:
        if v is None:
            return None
        if v < decimal.Decimal("1.0"):
            raise ValueError("overtime_hours must be >= 1.0")
        # First hour must be whole; after that 0.5 increments — equivalent to
        # saying the value is a multiple of 0.5.
        if (v * 2) != (v * 2).to_integral_value():
            raise ValueError("overtime_hours must be in 0.5 increments")
        return v


class BulkOverrideRequest(BaseModel):
    """Request to bulk-override punches for a month."""

    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)
    emp_id: Optional[str] = None  # HR+ only; defaults to self
    entries: list[BulkOverrideEntry] = Field(..., min_length=1)


class BulkOverrideDayResult(BaseModel):
    """Result for a single day after override."""

    date: str
    first_clock_in: Optional[str] = None
    last_clock_out: Optional[str] = None
    status: Optional[str] = None


class BulkOverrideResponse(BaseModel):
    """Response after bulk override."""

    emp_id: str
    updated_count: int
    results: list[BulkOverrideDayResult]
