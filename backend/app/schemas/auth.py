"""Authentication schemas for request/response validation."""

from pydantic import BaseModel, Field, field_validator

from app.utils.password import validate_password_strength


class LoginRequest(BaseModel):
    """Schema for login requests."""

    emp_id: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Schema for token responses."""

    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    """Schema for self-service password change."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_strength(cls, v: str) -> str:
        validate_password_strength(v)
        return v
