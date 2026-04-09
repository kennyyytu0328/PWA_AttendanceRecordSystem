"""Unit tests for WebAuthn service — Phase 3C (TDD)."""

import datetime
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.authenticator import Authenticator
from app.models.employee import Employee, Role
from app.services.webauthn_service import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication,
    verify_registration,
)


async def _create_employee(
    db_session: AsyncSession, emp_id: str = "EMP200"
) -> Employee:
    """Helper: insert an employee so FK constraints are satisfied."""
    emp = Employee(
        emp_id=emp_id,
        name="WebAuthn Tester",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()
    return emp


@dataclass
class _FakeCreationOptions:
    """Minimal stand-in for PublicKeyCredentialCreationOptions."""

    challenge: bytes = b"fake-challenge-reg"


@dataclass
class _FakeRequestOptions:
    """Minimal stand-in for PublicKeyCredentialRequestOptions."""

    challenge: bytes = b"fake-challenge-auth"


@dataclass
class _FakeVerifiedRegistration:
    """Minimal stand-in for VerifiedRegistration."""

    credential_id: bytes = b"cred-id-bytes"
    credential_public_key: bytes = b"public-key-bytes"
    sign_count: int = 0


@dataclass
class _FakeVerifiedAuthentication:
    """Minimal stand-in for VerifiedAuthentication."""

    credential_id: bytes = b"cred-id-bytes"
    new_sign_count: int = 1


# ---------- 1. generate_registration_options ----------


@patch("app.services.webauthn_service.options_to_json", return_value='{"mock":"options"}')
@patch("app.services.webauthn_service._gen_reg_opts", return_value=_FakeCreationOptions())
async def test_generate_registration_options(
    mock_gen_reg: MagicMock,
    mock_to_json: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Returns a JSON string of registration options for a given emp_id."""
    await _create_employee(db_session, "EMP200")

    result = await generate_registration_options(db_session, "EMP200")

    assert isinstance(result, str)
    assert result == '{"mock":"options"}'
    mock_gen_reg.assert_called_once()
    call_kwargs = mock_gen_reg.call_args.kwargs
    assert call_kwargs["rp_id"] == "localhost"
    assert call_kwargs["rp_name"] == "GoGoFresh Attendance"
    assert call_kwargs["user_name"] == "EMP200"
    mock_to_json.assert_called_once()


# ---------- 2. verify_registration_valid ----------


@patch(
    "app.services.webauthn_service._verify_reg_resp",
    return_value=_FakeVerifiedRegistration(),
)
async def test_verify_registration_valid(
    mock_verify: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Valid response stores credential in DB via authenticator repo."""
    await _create_employee(db_session, "EMP201")

    credential = {"id": "some-credential-data", "response": {}}
    challenge = b"test-challenge"

    auth = await verify_registration(db_session, "EMP201", credential, challenge)

    assert isinstance(auth, Authenticator)
    assert auth.emp_id == "EMP201"
    assert auth.public_key == b"public-key-bytes"
    assert auth.sign_count == 0
    mock_verify.assert_called_once()


# ---------- 3. verify_registration_invalid_response ----------


@patch(
    "app.services.webauthn_service._verify_reg_resp",
    side_effect=Exception("Invalid attestation"),
)
async def test_verify_registration_invalid_response(
    mock_verify: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Invalid response raises ValueError."""
    await _create_employee(db_session, "EMP202")

    credential = {"id": "bad-credential"}
    challenge = b"test-challenge"

    with pytest.raises(ValueError, match="registration verification failed"):
        await verify_registration(db_session, "EMP202", credential, challenge)


# ---------- 4. generate_authentication_options ----------


@patch(
    "app.services.webauthn_service.options_to_json",
    return_value='{"mock":"auth-options"}',
)
@patch(
    "app.services.webauthn_service._gen_auth_opts",
    return_value=_FakeRequestOptions(),
)
async def test_generate_authentication_options(
    mock_gen_auth: MagicMock,
    mock_to_json: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Returns options with allowCredentials for emp_id's registered credentials."""
    await _create_employee(db_session, "EMP203")

    # Pre-register a credential in the DB
    from app.repositories.authenticator_repository import create_authenticator

    await create_authenticator(
        db_session,
        Authenticator(
            credential_id="Y3JlZC1pZA",
            emp_id="EMP203",
            public_key=b"\x01\x02",
            sign_count=0,
        ),
    )

    result = await generate_authentication_options(db_session, "EMP203")

    assert isinstance(result, str)
    assert result == '{"mock":"auth-options"}'
    mock_gen_auth.assert_called_once()
    call_kwargs = mock_gen_auth.call_args.kwargs
    assert call_kwargs["rp_id"] == "localhost"
    assert len(call_kwargs["allow_credentials"]) == 1
    mock_to_json.assert_called_once()


# ---------- 5. generate_authentication_options_no_credentials ----------


async def test_generate_authentication_options_no_credentials(
    db_session: AsyncSession,
) -> None:
    """Raises ValueError when employee has no registered device."""
    await _create_employee(db_session, "EMP204")

    with pytest.raises(ValueError, match="no registered device"):
        await generate_authentication_options(db_session, "EMP204")


# ---------- 6. verify_authentication_valid ----------


@patch("app.services.webauthn_service._verify_auth_resp")
async def test_verify_authentication_valid(
    mock_verify: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Returns emp_id on successful authentication."""
    await _create_employee(db_session, "EMP205")

    from app.repositories.authenticator_repository import create_authenticator

    await create_authenticator(
        db_session,
        Authenticator(
            credential_id="cred_auth_valid",
            emp_id="EMP205",
            public_key=b"\xaa\xbb",
            sign_count=5,
        ),
    )

    mock_verify.return_value = _FakeVerifiedAuthentication(
        credential_id=b"cred_auth_valid",
        new_sign_count=6,
    )

    credential = {"id": "some-auth-credential"}
    challenge = b"auth-challenge"

    emp_id = await verify_authentication(
        db_session, "cred_auth_valid", credential, challenge
    )

    assert emp_id == "EMP205"
    mock_verify.assert_called_once()


# ---------- 7. verify_authentication_invalid_signature ----------


@patch(
    "app.services.webauthn_service._verify_auth_resp",
    side_effect=Exception("Invalid signature"),
)
async def test_verify_authentication_invalid_signature(
    mock_verify: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Raises ValueError on invalid authentication signature."""
    await _create_employee(db_session, "EMP206")

    from app.repositories.authenticator_repository import create_authenticator

    await create_authenticator(
        db_session,
        Authenticator(
            credential_id="cred_auth_bad",
            emp_id="EMP206",
            public_key=b"\xcc\xdd",
            sign_count=3,
        ),
    )

    credential = {"id": "bad-auth-credential"}
    challenge = b"auth-challenge"

    with pytest.raises(ValueError, match="authentication verification failed"):
        await verify_authentication(
            db_session, "cred_auth_bad", credential, challenge
        )


# ---------- 8. verify_authentication_updates_sign_count ----------


@patch("app.services.webauthn_service._verify_auth_resp")
async def test_verify_authentication_updates_sign_count(
    mock_verify: MagicMock,
    db_session: AsyncSession,
) -> None:
    """sign_count is updated in the DB after successful authentication."""
    await _create_employee(db_session, "EMP207")

    from app.repositories.authenticator_repository import (
        create_authenticator,
        find_by_credential_id,
    )

    await create_authenticator(
        db_session,
        Authenticator(
            credential_id="cred_sc_update",
            emp_id="EMP207",
            public_key=b"\x11\x22",
            sign_count=10,
        ),
    )

    mock_verify.return_value = _FakeVerifiedAuthentication(
        credential_id=b"cred_sc_update",
        new_sign_count=11,
    )

    credential = {"id": "sc-credential"}
    challenge = b"auth-challenge"

    await verify_authentication(
        db_session, "cred_sc_update", credential, challenge
    )

    updated = await find_by_credential_id(db_session, "cred_sc_update")
    assert updated is not None
    assert updated.sign_count == 11


# ---------- 9. verify_authentication_sign_count_regression ----------


@patch("app.services.webauthn_service._verify_auth_resp")
async def test_verify_authentication_sign_count_regression(
    mock_verify: MagicMock,
    db_session: AsyncSession,
) -> None:
    """If new sign_count <= old sign_count, raise ValueError (clone detection)."""
    await _create_employee(db_session, "EMP208")

    from app.repositories.authenticator_repository import create_authenticator

    await create_authenticator(
        db_session,
        Authenticator(
            credential_id="cred_clone",
            emp_id="EMP208",
            public_key=b"\x33\x44",
            sign_count=10,
        ),
    )

    # new_sign_count == old sign_count (regression / clone)
    mock_verify.return_value = _FakeVerifiedAuthentication(
        credential_id=b"cred_clone",
        new_sign_count=10,
    )

    credential = {"id": "clone-credential"}
    challenge = b"auth-challenge"

    with pytest.raises(ValueError, match="clone"):
        await verify_authentication(
            db_session, "cred_clone", credential, challenge
        )


# ---------- 10. multiple_authenticators_per_employee ----------


@patch("app.services.webauthn_service._verify_reg_resp")
async def test_multiple_authenticators_per_employee(
    mock_verify: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Employee can register multiple devices."""
    await _create_employee(db_session, "EMP209")

    mock_verify.side_effect = [
        _FakeVerifiedRegistration(
            credential_id=b"device-1-id",
            credential_public_key=b"pk-1",
            sign_count=0,
        ),
        _FakeVerifiedRegistration(
            credential_id=b"device-2-id",
            credential_public_key=b"pk-2",
            sign_count=0,
        ),
    ]

    auth1 = await verify_registration(
        db_session, "EMP209", {"id": "dev1"}, b"challenge-1"
    )
    auth2 = await verify_registration(
        db_session, "EMP209", {"id": "dev2"}, b"challenge-2"
    )

    assert auth1.emp_id == "EMP209"
    assert auth2.emp_id == "EMP209"
    assert auth1.credential_id != auth2.credential_id

    from app.repositories.authenticator_repository import find_by_employee_id

    all_auths = await find_by_employee_id(db_session, "EMP209")
    assert len(all_auths) == 2
