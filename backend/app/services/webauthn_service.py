"""WebAuthn service — registration and authentication flows."""

from webauthn import (
    generate_authentication_options as _gen_auth_opts,
    generate_registration_options as _gen_reg_opts,
    options_to_json,
    verify_authentication_response as _verify_auth_resp,
    verify_registration_response as _verify_reg_resp,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.authenticator import Authenticator
from app.repositories import authenticator_repository

# In-memory challenge store (will migrate to Redis later)
_challenges: dict[str, bytes] = {}


async def generate_registration_options(
    session: AsyncSession, emp_id: str
) -> str:
    """Generate WebAuthn registration options and return as JSON string.

    Stores the challenge for later verification.
    """
    existing = await authenticator_repository.find_by_employee_id(session, emp_id)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(auth.credential_id))
        for auth in existing
    ]

    options = _gen_reg_opts(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_name=emp_id,
        exclude_credentials=exclude_credentials if exclude_credentials else None,
    )

    _challenges[emp_id] = options.challenge

    return options_to_json(options)


async def verify_registration(
    session: AsyncSession,
    emp_id: str,
    credential: dict,
    challenge: bytes,
) -> Authenticator:
    """Verify a WebAuthn registration response and persist the credential.

    Raises ValueError if the response is invalid.
    """
    try:
        verification = _verify_reg_resp(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
        )
    except Exception as exc:
        raise ValueError(f"registration verification failed: {exc}") from exc

    credential_id = bytes_to_base64url(verification.credential_id)

    authenticator = Authenticator(
        credential_id=credential_id,
        emp_id=emp_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
    )

    return await authenticator_repository.create_authenticator(session, authenticator)


async def generate_authentication_options(
    session: AsyncSession, emp_id: str
) -> str:
    """Generate WebAuthn authentication options and return as JSON string.

    Raises ValueError if the employee has no registered devices.
    """
    existing = await authenticator_repository.find_by_employee_id(session, emp_id)

    if not existing:
        raise ValueError("no registered device")

    allow_credentials = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(auth.credential_id))
        for auth in existing
    ]

    options = _gen_auth_opts(
        rp_id=settings.webauthn_rp_id,
        allow_credentials=allow_credentials,
    )

    _challenges[emp_id] = options.challenge

    return options_to_json(options)


async def verify_authentication(
    session: AsyncSession,
    credential_id: str,
    credential: dict,
    challenge: bytes,
) -> str:
    """Verify a WebAuthn authentication response.

    Returns the emp_id on success.
    Raises ValueError if verification fails or sign_count regresses (clone detection).
    """
    stored = await authenticator_repository.find_by_credential_id(
        session, credential_id
    )
    if stored is None:
        raise ValueError(f"credential {credential_id} not found")

    try:
        verification = _verify_auth_resp(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
        )
    except Exception as exc:
        raise ValueError(f"authentication verification failed: {exc}") from exc

    new_sign_count = verification.new_sign_count

    if new_sign_count <= stored.sign_count:
        raise ValueError(
            f"potential authenticator clone detected: "
            f"new sign_count ({new_sign_count}) <= "
            f"current sign_count ({stored.sign_count})"
        )

    await authenticator_repository.update_sign_count(
        session, credential_id, new_sign_count
    )

    return stored.emp_id


def _is_hex(value: str) -> bool:
    """Check if a string is valid hexadecimal."""
    try:
        bytes.fromhex(value)
        return True
    except ValueError:
        return False
