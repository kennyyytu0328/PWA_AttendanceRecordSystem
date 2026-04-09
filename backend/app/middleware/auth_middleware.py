"""Auth middleware — JWT validation, user injection, role-based access control.

Provides two FastAPI dependencies:
- ``get_current_user``: extracts and validates JWT from Authorization header.
- ``require_role(minimum_role)``: ensures the caller has at least the given role.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.models.employee import Role

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
) -> dict:
    """Decode and validate a JWT Bearer token.

    Returns the token payload dict with at least ``sub`` (emp_id) and ``role``.

    Raises
    ------
    HTTPException 401
        If the token is missing, expired, malformed, or has an invalid signature.
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
