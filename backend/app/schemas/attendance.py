"""Attendance schemas for request/response validation."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.attendance_log import WorkMode


class PunchRequest(BaseModel):
    """Schema for a clock-in/out punch request."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: float = Field(..., ge=0)
    webauthn_response: dict


class PunchGPSRequest(BaseModel):
    """Schema for a GPS-only punch request (no WebAuthn challenge)."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: float = Field(..., ge=0)


class OverrideRequest(BaseModel):
    """Schema for a manager-initiated attendance override."""

    target_emp_id: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: float = Field(..., ge=0)
    work_mode: WorkMode


class AttendanceLogResponse(BaseModel):
    """Schema for attendance log responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    emp_id: str
    timestamp: datetime.datetime
    latitude: float
    longitude: float
    accuracy: float
    ip_address: str
    work_mode: WorkMode
    is_overridden: bool


class PunchResponse(BaseModel):
    """Schema for the result of a punch operation."""

    work_mode: WorkMode
    distance_km: float
    is_low_accuracy: bool
    log: AttendanceLogResponse
    tardiness_status: str | None = None
    summary_id: int | None = None
