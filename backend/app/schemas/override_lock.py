"""Schemas for the month-end override lock."""
from pydantic import BaseModel


class OverrideLockResponse(BaseModel):
    locked: bool


class OverrideLockUpdateRequest(BaseModel):
    locked: bool
