"""Schemas for Phase 15C org-hierarchy config endpoints."""

from pydantic import BaseModel, Field


class RanksResponse(BaseModel):
    ranks: list[str]


class RanksUpdateRequest(BaseModel):
    ranks: list[str] = Field(..., min_length=0, max_length=50)


class OrgScopingResponse(BaseModel):
    enabled: bool


class OrgScopingUpdateRequest(BaseModel):
    enabled: bool
