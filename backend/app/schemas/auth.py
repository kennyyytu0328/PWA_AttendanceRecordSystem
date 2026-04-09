"""Authentication schemas for request/response validation."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Schema for login requests."""

    emp_id: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Schema for token responses."""

    access_token: str
    token_type: str = "bearer"
