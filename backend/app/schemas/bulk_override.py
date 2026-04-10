"""Schemas for bulk punch override."""

from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BulkOverrideEntry(BaseModel):
    """A single day's override data."""

    date: datetime.date
    first_clock_in: Optional[datetime.time] = None
    last_clock_out: Optional[datetime.time] = None


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
