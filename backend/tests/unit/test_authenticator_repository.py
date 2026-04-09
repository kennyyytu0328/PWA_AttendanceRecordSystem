"""Unit tests for Authenticator Repository — Phase 2B (TDD)."""

import datetime

from app.models.authenticator import Authenticator
from app.models.employee import Employee, Role


async def _create_employee(db_session, emp_id: str = "EMP100") -> Employee:
    """Helper: insert an employee so FK constraints are satisfied."""
    emp = Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    return emp


# ---------- 1. create_authenticator ----------
async def test_create_authenticator(db_session):
    """Stores a WebAuthn credential for an employee and returns it."""
    from app.repositories.authenticator_repository import create_authenticator

    await _create_employee(db_session, "EMP100")

    auth = Authenticator(
        credential_id="cred_aaa",
        emp_id="EMP100",
        public_key=b"\x01\x02\x03",
        sign_count=0,
    )
    result = await create_authenticator(db_session, auth)

    assert result.credential_id == "cred_aaa"
    assert result.emp_id == "EMP100"
    assert result.public_key == b"\x01\x02\x03"
    assert result.sign_count == 0


# ---------- 2. find_by_credential_id ----------
async def test_find_by_credential_id(db_session):
    """Retrieves an authenticator by its credential_id."""
    from app.repositories.authenticator_repository import (
        create_authenticator,
        find_by_credential_id,
    )

    await _create_employee(db_session, "EMP101")

    auth = Authenticator(
        credential_id="cred_bbb",
        emp_id="EMP101",
        public_key=b"\xaa\xbb",
        sign_count=5,
    )
    await create_authenticator(db_session, auth)

    found = await find_by_credential_id(db_session, "cred_bbb")
    assert found is not None
    assert found.credential_id == "cred_bbb"
    assert found.emp_id == "EMP101"
    assert found.sign_count == 5

    # Non-existent credential returns None
    missing = await find_by_credential_id(db_session, "cred_nonexistent")
    assert missing is None


# ---------- 3. find_by_employee_id ----------
async def test_find_by_employee_id(db_session):
    """Returns all authenticators registered for an employee."""
    from app.repositories.authenticator_repository import (
        create_authenticator,
        find_by_employee_id,
    )

    await _create_employee(db_session, "EMP102")

    auth1 = Authenticator(
        credential_id="cred_c1",
        emp_id="EMP102",
        public_key=b"\x10",
        sign_count=0,
    )
    auth2 = Authenticator(
        credential_id="cred_c2",
        emp_id="EMP102",
        public_key=b"\x20",
        sign_count=3,
    )
    await create_authenticator(db_session, auth1)
    await create_authenticator(db_session, auth2)

    results = await find_by_employee_id(db_session, "EMP102")
    assert len(results) == 2
    cred_ids = {r.credential_id for r in results}
    assert cred_ids == {"cred_c1", "cred_c2"}

    # Employee with no authenticators returns empty list
    empty = await find_by_employee_id(db_session, "EMP_NO_AUTH")
    assert empty == []


# ---------- 4. update_sign_count ----------
async def test_update_sign_count(db_session):
    """Updates the sign_count and returns the updated record."""
    from app.repositories.authenticator_repository import (
        create_authenticator,
        update_sign_count,
    )

    await _create_employee(db_session, "EMP103")

    auth = Authenticator(
        credential_id="cred_ddd",
        emp_id="EMP103",
        public_key=b"\xff",
        sign_count=10,
    )
    await create_authenticator(db_session, auth)

    updated = await update_sign_count(db_session, "cred_ddd", 11)
    assert updated is not None
    assert updated.sign_count == 11

    # Non-existent credential returns None
    missing = await update_sign_count(db_session, "cred_ghost", 99)
    assert missing is None


# ---------- 5. delete_authenticator ----------
async def test_delete_authenticator(db_session):
    """Removes a credential and returns True; returns False if not found."""
    from app.repositories.authenticator_repository import (
        create_authenticator,
        delete_authenticator,
        find_by_credential_id,
    )

    await _create_employee(db_session, "EMP104")

    auth = Authenticator(
        credential_id="cred_eee",
        emp_id="EMP104",
        public_key=b"\xde\xad",
        sign_count=0,
    )
    await create_authenticator(db_session, auth)

    deleted = await delete_authenticator(db_session, "cred_eee")
    assert deleted is True

    # Verify it is gone
    gone = await find_by_credential_id(db_session, "cred_eee")
    assert gone is None

    # Deleting non-existent credential returns False
    not_found = await delete_authenticator(db_session, "cred_nonexistent")
    assert not_found is False
