"""Unit tests for WebAuthn challenge repository — DB-backed, worker-safe store.

The challenge persists in PostgreSQL (not per-process memory) so the two-step
WebAuthn ceremony survives the verify request landing on a different uvicorn
worker than the one that generated the challenge. Challenges are single-use
(consumed on read) and expire after a short TTL.
"""

import datetime

from app.models.employee import Employee, Role
from app.models.webauthn_challenge import WebAuthnChallenge
from app.repositories import webauthn_challenge_repository as repo


async def _create_employee(db_session, emp_id: str = "EMP300") -> Employee:
    """Helper: insert an employee so the FK constraint is satisfied."""
    emp = Employee(
        emp_id=emp_id,
        name="Challenge Tester",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    return emp


async def test_set_and_consume_roundtrip(db_session) -> None:
    """A stored challenge is returned byte-for-byte by consume."""
    await _create_employee(db_session, "EMP300")
    challenge = b"\x01\x02\x03\xfe\xff random-bytes"

    await repo.set_challenge(db_session, "EMP300", challenge)
    consumed = await repo.consume_challenge(db_session, "EMP300")

    assert consumed == challenge


async def test_consume_missing_returns_none(db_session) -> None:
    """Consuming when no challenge exists returns None (no error)."""
    result = await repo.consume_challenge(db_session, "NOBODY")
    assert result is None


async def test_consume_is_single_use(db_session) -> None:
    """A challenge can only be consumed once; the second read returns None."""
    await _create_employee(db_session, "EMP301")
    await repo.set_challenge(db_session, "EMP301", b"one-shot")

    first = await repo.consume_challenge(db_session, "EMP301")
    second = await repo.consume_challenge(db_session, "EMP301")

    assert first == b"one-shot"
    assert second is None


async def test_set_overwrites_existing(db_session) -> None:
    """Re-generating replaces the prior challenge (only the latest is valid)."""
    await _create_employee(db_session, "EMP302")

    await repo.set_challenge(db_session, "EMP302", b"first-challenge")
    await repo.set_challenge(db_session, "EMP302", b"second-challenge")

    consumed = await repo.consume_challenge(db_session, "EMP302")
    assert consumed == b"second-challenge"


async def test_consume_expired_returns_none_and_deletes(db_session) -> None:
    """A challenge older than the TTL is treated as missing and removed."""
    await _create_employee(db_session, "EMP303")

    stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)
    from webauthn.helpers import bytes_to_base64url

    db_session.add(
        WebAuthnChallenge(
            emp_id="EMP303",
            challenge=bytes_to_base64url(b"too-old"),
            created_at=stale,
        )
    )
    await db_session.commit()

    # Default TTL (300s) — the 10-minute-old challenge is expired.
    result = await repo.consume_challenge(db_session, "EMP303")
    assert result is None

    # Expired rows are still consumed (deleted), not left to accumulate.
    leftover = await repo.consume_challenge(db_session, "EMP303")
    assert leftover is None
