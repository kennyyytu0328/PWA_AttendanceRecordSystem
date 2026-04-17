"""Authentication router — login, WebAuthn registration/authentication, /me."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.middleware.rate_limiter import (
    check_rate_limit,
    record_failed_attempt,
    reset_rate_limit,
)
from app.repositories import authenticator_repository
from app.schemas.auth import LoginRequest, TokenResponse
from app.services import employee_service, webauthn_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Authenticate with emp_id + password, return JWT."""
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{body.emp_id}"

    check_rate_limit(rate_limit_key)

    try:
        result = await employee_service.authenticate(
            session, body.emp_id, body.password
        )
    except ValueError:
        record_failed_attempt(rate_limit_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    reset_rate_limit(rate_limit_key)
    return result


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Return the current authenticated user's identity."""
    return {"emp_id": user["sub"], "role": user["role"]}


@router.get("/webauthn/status")
async def webauthn_status(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Check if the authenticated user has registered WebAuthn credentials."""
    credentials = await authenticator_repository.find_by_employee_id(
        session, user["sub"]
    )
    return {"registered": len(credentials) > 0, "count": len(credentials)}


@router.delete("/webauthn/credentials")
async def delete_webauthn_credentials(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete all WebAuthn credentials for the authenticated user."""
    count = await authenticator_repository.delete_all_by_employee(
        session, user["sub"]
    )
    return {"deleted": count}


@router.post("/register/generate-options")
async def register_generate_options(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Generate WebAuthn registration options for the authenticated user."""
    options_json = await webauthn_service.generate_registration_options(
        session, user["sub"]
    )
    return json.loads(options_json)


@router.post("/register/verify")
async def register_verify(
    body: dict,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Verify a WebAuthn registration response and store the credential."""
    emp_id = user["sub"]
    challenge = webauthn_service._challenges.get(emp_id)
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending registration challenge",
        )

    try:
        await webauthn_service.verify_registration(
            session, emp_id, body, challenge
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return {"status": "ok"}


@router.post("/authenticate/generate-options")
async def authenticate_generate_options(
    body: dict,
    session: AsyncSession = Depends(get_db),
):
    """Generate WebAuthn authentication options for a given employee."""
    emp_id = body.get("emp_id")
    if not emp_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="emp_id is required",
        )

    try:
        options_json = await webauthn_service.generate_authentication_options(
            session, emp_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return json.loads(options_json)


@router.post("/authenticate/verify")
async def authenticate_verify(
    body: dict,
    session: AsyncSession = Depends(get_db),
):
    """Verify a WebAuthn authentication response and return JWT."""
    credential_id = body.get("id")
    emp_id = body.get("emp_id")

    if not credential_id or not emp_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="credential id and emp_id are required",
        )

    challenge = webauthn_service._challenges.get(emp_id)
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending authentication challenge",
        )

    try:
        verified_emp_id = await webauthn_service.verify_authentication(
            session, credential_id, body, challenge
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Issue JWT for the verified employee
    from app.repositories import employee_repository
    employee = await employee_repository.find_by_id(session, verified_emp_id)
    if employee is None or employee.terminated_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Employee not found",
        )

    from datetime import UTC, datetime, timedelta
    from jose import jwt as jose_jwt
    from app.config import settings

    payload = {
        "sub": employee.emp_id,
        "role": employee.role.value,
        "exp": datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes,
        ),
    }
    token = jose_jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

    return TokenResponse(access_token=token)
