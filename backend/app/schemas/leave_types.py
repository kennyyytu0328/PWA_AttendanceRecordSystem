"""Schemas for leave-types config endpoints."""

from pydantic import BaseModel, Field


class LeaveTypesResponse(BaseModel):
    leave_types: list[str]


class LeaveTypesUpdateRequest(BaseModel):
    leave_types: list[str] = Field(..., min_length=0, max_length=100)
