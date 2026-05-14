"""Schemas for leave-types config endpoints."""

from pydantic import BaseModel, Field


class LeaveTypesResponse(BaseModel):
    types: list[str]


class LeaveTypesUpdateRequest(BaseModel):
    types: list[str] = Field(..., min_length=0, max_length=100)
