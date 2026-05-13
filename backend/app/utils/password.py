from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


_MIN_LENGTH = 8
_MAX_LENGTH = 128


def validate_password_strength(plain: str) -> None:
    """Validate a candidate password against project policy.

    Policy: at least 8 chars, at most 128 chars, must contain at least one digit.

    Raises
    ------
    ValueError
        If the password does not meet the policy. The error message
        identifies which rule was violated.
    """
    if len(plain) < _MIN_LENGTH:
        raise ValueError(f"password must be at least {_MIN_LENGTH} characters")
    if len(plain) > _MAX_LENGTH:
        raise ValueError(f"password must be at most {_MAX_LENGTH} characters")
    if not any(c.isdigit() for c in plain):
        raise ValueError("password must contain at least one digit")
