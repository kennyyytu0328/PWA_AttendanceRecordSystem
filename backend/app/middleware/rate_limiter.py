"""In-memory rate limiter for login attempts.

Tracks failed login attempts per key (IP or emp_id) using a simple dict
with timestamps. No external dependencies (Redis) required.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class _RateLimitConfig:
    max_attempts: int = 5
    window_seconds: int = 60


_config = _RateLimitConfig()

# Mapping of key -> list of timestamps of failed attempts
_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _cleanup_old_attempts(key: str, now: float) -> list[float]:
    """Return only attempts within the current time window (immutable style)."""
    cutoff = now - _config.window_seconds
    recent = [ts for ts in _failed_attempts.get(key, []) if ts > cutoff]
    return recent


def check_rate_limit(key: str) -> None:
    """Raise 429 if the key has exceeded the max attempts within the window.

    Should be called BEFORE attempting authentication.

    Raises
    ------
    HTTPException 429
        If the rate limit has been exceeded.
    """
    now = time.monotonic()
    recent = _cleanup_old_attempts(key, now)
    _failed_attempts[key] = recent

    if len(recent) >= _config.max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )


def record_failed_attempt(key: str) -> None:
    """Record a failed login attempt for the given key."""
    now = time.monotonic()
    recent = _cleanup_old_attempts(key, now)
    _failed_attempts[key] = [*recent, now]


def reset_rate_limit(key: str) -> None:
    """Clear all recorded attempts for the given key (e.g., on successful login)."""
    _failed_attempts.pop(key, None)


def clear_all() -> None:
    """Clear all rate limit state. Useful for testing."""
    _failed_attempts.clear()
