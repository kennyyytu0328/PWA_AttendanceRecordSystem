"""WebAuthn challenge repository — DB-backed, worker-safe challenge store.

The WebAuthn ceremony spans two HTTP requests (generate-options, then verify).
Storing the challenge in PostgreSQL instead of per-process memory means the
verify request can be served by any uvicorn worker and still find the challenge.
Challenges are single-use (consumed on read) and short-lived (TTL), which also
hardens replay resistance compared with the previous never-expiring in-memory map.
"""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from app.models.webauthn_challenge import WebAuthnChallenge

# The browser ceremony takes seconds, not minutes. A short TTL bounds replay
# risk and stops stale rows accumulating if a ceremony is abandoned.
CHALLENGE_TTL_SECONDS = 300


async def set_challenge(
    session: AsyncSession, emp_id: str, challenge: bytes
) -> None:
    """Store (upsert) the pending challenge for *emp_id*.

    Overwrites any existing challenge so only the most recent ceremony is valid.
    """
    encoded = bytes_to_base64url(challenge)
    now = datetime.datetime.now(datetime.UTC)

    result = await session.execute(
        select(WebAuthnChallenge).where(WebAuthnChallenge.emp_id == emp_id)
    )
    existing = result.scalars().first()

    if existing is None:
        session.add(
            WebAuthnChallenge(emp_id=emp_id, challenge=encoded, created_at=now)
        )
    else:
        existing.challenge = encoded
        existing.created_at = now
        session.add(existing)

    await session.commit()


async def consume_challenge(
    session: AsyncSession,
    emp_id: str,
    *,
    ttl_seconds: int = CHALLENGE_TTL_SECONDS,
) -> bytes | None:
    """Fetch, delete, and return the pending challenge for *emp_id*.

    Single-use: the row is always deleted when present. Returns None when there
    is no pending challenge or it has expired (older than *ttl_seconds*).
    """
    result = await session.execute(
        select(WebAuthnChallenge).where(WebAuthnChallenge.emp_id == emp_id)
    )
    row = result.scalars().first()
    if row is None:
        return None

    created_at = row.created_at
    challenge = base64url_to_bytes(row.challenge)

    # Always consume (single-use), even when expired, so stale rows don't linger.
    await session.delete(row)
    await session.commit()

    # Normalize tz-naive datetimes (e.g. a SQLite round-trip) to UTC-aware
    # before comparing — mirrors the password_changed_at handling in auth.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=datetime.UTC)

    age = datetime.datetime.now(datetime.UTC) - created_at
    if age > datetime.timedelta(seconds=ttl_seconds):
        return None

    return challenge
