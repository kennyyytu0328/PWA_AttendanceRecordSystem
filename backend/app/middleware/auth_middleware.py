"""Auth middleware — JWT validation, user injection, role-based access control.

Provides two FastAPI dependencies:
- ``get_current_user``: extracts and validates JWT from Authorization header.
- ``require_role(minimum_role)``: ensures the caller has at least the given role.
"""

import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.employee import Role
from app.repositories import employee_repository

# ---------------------------------------------------------------------------
# Role hierarchy — higher index = more privileges
# ---------------------------------------------------------------------------
_ROLE_HIERARCHY: list[Role] = [Role.EMPLOYEE, Role.MANAGER, Role.HR, Role.ADMIN]


def _role_level(role: Role) -> int:
    """Return the numeric level of a role in the hierarchy."""
    return _ROLE_HIERARCHY.index(role)


# ---------------------------------------------------------------------------
# Bearer token extraction
# ---------------------------------------------------------------------------
_bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Decode and validate a JWT Bearer token.

    Also enforces revocation via ``password_changed_at``: if the token's
    ``iat`` predates the employee's most recent password change, reject.
    Legacy employees with ``password_changed_at IS NULL`` and tokens issued
    before the iat-claim rollout are exempt — both skip the check.

    Tokens of terminated employees (``terminated_at IS NOT NULL``) are
    rejected outright — with week-long tokens, blocking login alone would
    leave an already-issued token usable long after termination. Reversible:
    reactivation makes still-unexpired tokens valid again.

    Returns the token payload dict with at least ``sub`` and ``role``.

    Raises
    ------
    HTTPException 401
        If the token is missing, expired, malformed, has an invalid signature,
        or has been revoked by a subsequent password change.
    """
    if credentials is None:
        raise _CREDENTIALS_ERROR

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if "sub" not in payload or "role" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload incomplete",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Revocation check: reject if token's iat < employee.password_changed_at.
    # Tokens without iat (issued before Task 4 shipped) skip the check entirely
    # to preserve backward compatibility.
    iat = payload.get("iat")
    if iat is not None:
        employee = await employee_repository.find_by_id(session, payload["sub"])
        if employee is not None and employee.terminated_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account has been deactivated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if (
            employee is not None
            and employee.password_changed_at is not None
        ):
            iat_dt = datetime.datetime.fromtimestamp(iat, tz=datetime.UTC)
            changed_at = employee.password_changed_at
            # Normalise to UTC-aware if the DB returns a naive datetime
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=datetime.UTC)
            # JWT iat is whole seconds (NumericDate); drop microseconds on the
            # DB side so a token issued within the same second as the password
            # change is not falsely revoked.
            changed_at = changed_at.replace(microsecond=0)
            if iat_dt < changed_at:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    return payload


# ---------------------------------------------------------------------------
# Role-based dependency factory
# ---------------------------------------------------------------------------
def require_role(minimum_role: Role):
    """Return a FastAPI dependency that enforces a minimum role level.

    The dependency resolves to the user payload dict if the caller's role
    is >= *minimum_role* in the hierarchy (EMPLOYEE < MANAGER < HR < ADMIN).

    Raises
    ------
    HTTPException 403
        If the caller's role is below the required minimum.
    """

    async def _check_role(
        user: dict = Depends(get_current_user),
    ) -> dict:
        try:
            user_role = Role(user["role"])
        except (ValueError, KeyError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid role in token",
            )

        if _role_level(user_role) < _role_level(minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least {minimum_role.value} role",
            )

        return user

    return Depends(_check_role)
