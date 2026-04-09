"""System config schemas for request/response validation."""

import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SystemConfigUpdate(BaseModel):
    """Schema for updating a system config entry."""

    key: str = Field(..., min_length=1)
    value: dict[str, Any]


class SystemConfigResponse(BaseModel):
    """Schema for system config responses."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Optional[dict[str, Any]] = None
    updated_by: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None
