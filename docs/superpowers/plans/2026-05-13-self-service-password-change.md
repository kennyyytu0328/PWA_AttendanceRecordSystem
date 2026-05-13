# Self-Service Password Change Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any authenticated employee change their own password via `/dashboard/change-password`, with re-auth required and forced re-login on every device after success.

**Architecture:** New `POST /api/auth/change-password` endpoint validates the current password, writes a new bcrypt hash, and bumps a `password_changed_at` timestamp on the employee. The existing JWT middleware learns one new rule: reject any token whose `iat` claim predates that timestamp. Frontend gets a Zod-validated form page and a quick-action card.

**Tech Stack:** FastAPI · SQLModel · Alembic · python-jose (JWT) · passlib (bcrypt) · pytest-asyncio · Next.js (App Router) · React · Zod · vitest · next-intl

**Spec:** `docs/superpowers/specs/2026-05-13-self-service-password-change-design.md`

---

## File Map

**Created:**
- `backend/alembic/versions/e5f6a7b8c9d0_add_password_changed_at_to_employees.py`
- `backend/tests/unit/test_password_validator.py`
- `backend/tests/unit/test_change_password_schema.py`
- `backend/tests/unit/test_change_password_service.py`
- `backend/tests/integration/test_change_password_endpoint.py`
- `backend/tests/integration/test_jwt_iat_revocation.py`
- `frontend/src/app/dashboard/change-password/page.tsx`
- `frontend/src/components/ChangePasswordForm.tsx`
- `frontend/src/components/__tests__/ChangePasswordForm.test.tsx`
- `frontend/src/lib/__tests__/changePasswordSchema.test.ts`

**Modified:**
- `backend/app/models/employee.py` (add column)
- `backend/app/utils/password.py` (add `validate_password_strength`)
- `backend/app/schemas/auth.py` (add `ChangePasswordRequest`)
- `backend/app/services/employee_service.py` (add `change_password`; add `iat` to JWT issuance in `authenticate`)
- `backend/app/routers/auth.py` (new handler + add `iat` to JWT issued by `authenticate_verify`)
- `backend/app/middleware/auth_middleware.py` (enforce `iat ≥ password_changed_at`)
- `frontend/src/lib/validators.ts` (add `changePasswordSchema`)
- `frontend/src/lib/api.ts` is **not** modified — we use existing `apiClient.post` directly
- `frontend/src/app/dashboard/page.tsx` (add NavLinkCard)
- `frontend/src/messages/en.json` (add `changePassword.*`)
- `frontend/src/messages/zh.json` (add `changePassword.*`)

**Conventions to follow:**
- Backend: `datetime.now(UTC)` (not `utcnow()`); module-level async functions in services; `ValueError` from services maps to HTTP errors in routers.
- Frontend: read `node_modules/next/dist/docs/` before writing app-router code (per `frontend/AGENTS.md`). i18n via `useTranslation` from `@/lib/i18n`. Errors in `apiClient` come back as `ApiError` with `status` and `detail`.

---

## Phase 1 — Backend Foundation

### Task 1: Add `password_changed_at` column to Employee model + Alembic migration

**Files:**
- Modify: `backend/app/models/employee.py`
- Create: `backend/alembic/versions/e5f6a7b8c9d0_add_password_changed_at_to_employees.py`

- [ ] **Step 1: Add the field to `Employee` model**

Edit `backend/app/models/employee.py`. After the `terminated_at` field (around line 37–40), append:

```python
    password_changed_at: datetime.datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
```

No index — only read on the per-request employee load that is already keyed by primary key.

- [ ] **Step 2: Create the Alembic migration file**

Create `backend/alembic/versions/e5f6a7b8c9d0_add_password_changed_at_to_employees.py`:

```python
"""add password_changed_at to employees

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-13 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable password_changed_at timestamp column to employees."""
    op.add_column(
        "employees",
        sa.Column(
            "password_changed_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("employees", "password_changed_at")
```

- [ ] **Step 3: Run the migration locally**

```bash
cd backend
alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade d4e5f6a7b8c9 -> e5f6a7b8c9d0, add password_changed_at to employees`

- [ ] **Step 4: Verify the existing test suite still passes**

```bash
cd backend
pytest -q
```

Expected: all 279 existing tests pass — the new nullable column is invisible to existing flows.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/employee.py backend/alembic/versions/e5f6a7b8c9d0_add_password_changed_at_to_employees.py
git commit -m "feat(db): add password_changed_at column to employees"
```

---

### Task 2: Add `validate_password_strength` utility (TDD)

**Files:**
- Create: `backend/tests/unit/test_password_validator.py`
- Modify: `backend/app/utils/password.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/unit/test_password_validator.py`:

```python
"""Unit tests for password-strength validator."""

import pytest

from app.utils.password import validate_password_strength


class TestValidatePasswordStrength:
    def test_accepts_8_chars_with_digit(self) -> None:
        validate_password_strength("abcdefg1")  # no raise

    def test_accepts_128_char_max(self) -> None:
        validate_password_strength("a1" * 64)  # exactly 128 chars

    def test_rejects_too_short(self) -> None:
        with pytest.raises(ValueError, match="at least 8"):
            validate_password_strength("abc1")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="at least 8"):
            validate_password_strength("")

    def test_rejects_no_digit(self) -> None:
        with pytest.raises(ValueError, match="digit"):
            validate_password_strength("abcdefgh")

    def test_rejects_over_128_chars(self) -> None:
        with pytest.raises(ValueError, match="at most 128"):
            validate_password_strength("a1" * 65)  # 130 chars
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
pytest tests/unit/test_password_validator.py -v
```

Expected: `ImportError` or `AttributeError` — `validate_password_strength` doesn't exist yet.

- [ ] **Step 3: Implement the validator**

Edit `backend/app/utils/password.py`. Append to the file:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_password_validator.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/password.py backend/tests/unit/test_password_validator.py
git commit -m "feat(backend): add password strength validator"
```

---

### Task 3: Add `ChangePasswordRequest` schema (TDD)

**Files:**
- Create: `backend/tests/unit/test_change_password_schema.py`
- Modify: `backend/app/schemas/auth.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/unit/test_change_password_schema.py`:

```python
"""Unit tests for ChangePasswordRequest schema."""

import pytest
from pydantic import ValidationError

from app.schemas.auth import ChangePasswordRequest


class TestChangePasswordRequest:
    def test_accepts_valid_payload(self) -> None:
        req = ChangePasswordRequest(
            current_password="oldPass1", new_password="newPass1!"
        )
        assert req.current_password == "oldPass1"
        assert req.new_password == "newPass1!"

    def test_rejects_empty_current(self) -> None:
        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="", new_password="newPass1!")

    def test_rejects_short_new_password(self) -> None:
        with pytest.raises(ValidationError):
            ChangePasswordRequest(
                current_password="oldPass1", new_password="short1"
            )

    def test_rejects_new_password_without_digit(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ChangePasswordRequest(
                current_password="oldPass1", new_password="abcdefgh"
            )
        assert "digit" in str(exc.value).lower()

    def test_rejects_new_password_over_128_chars(self) -> None:
        with pytest.raises(ValidationError):
            ChangePasswordRequest(
                current_password="oldPass1", new_password="a1" * 65
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_change_password_schema.py -v
```

Expected: `ImportError` — `ChangePasswordRequest` doesn't exist yet.

- [ ] **Step 3: Add the schema**

Edit `backend/app/schemas/auth.py`. Add at the bottom:

```python
from pydantic import field_validator

from app.utils.password import validate_password_strength


class ChangePasswordRequest(BaseModel):
    """Schema for self-service password change."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_strength(cls, v: str) -> str:
        validate_password_strength(v)
        return v
```

(If `from pydantic import field_validator` would create a duplicate import, merge it with the existing pydantic import line at the top.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_change_password_schema.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/auth.py backend/tests/unit/test_change_password_schema.py
git commit -m "feat(backend): add ChangePasswordRequest schema"
```

---

## Phase 2 — Backend Service & JWT

### Task 4: Add `iat` claim to JWT issuance (both paths)

**Files:**
- Modify: `backend/app/services/employee_service.py:69-78` (password login)
- Modify: `backend/app/routers/auth.py:190-199` (WebAuthn login)

- [ ] **Step 1: Write a failing test that asserts `iat` is in the token**

Create `backend/tests/unit/test_jwt_iat_claim.py`:

```python
"""Verify both JWT issuance paths set the `iat` claim."""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee, Role
from app.services import employee_service
from app.utils.password import hash_password


@pytest.mark.asyncio
async def test_password_login_sets_iat(db_session: AsyncSession) -> None:
    employee = Employee(
        emp_id="IAT001",
        name="IAT User",
        department="X",
        role=Role.EMPLOYEE,
        hashed_password=hash_password("pass1234"),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(employee)
    await db_session.commit()

    result = await employee_service.authenticate(db_session, "IAT001", "pass1234")

    payload: dict[str, Any] = jose_jwt.decode(
        result.access_token, settings.secret_key, algorithms=[settings.algorithm]
    )
    assert "iat" in payload
    assert isinstance(payload["iat"], int)
```

(The fixture `db_session` is the existing project fixture used by other integration/unit DB tests — check `backend/tests/conftest.py` for the exact name and adapt if it differs.)

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_jwt_iat_claim.py -v
```

Expected: AssertionError — `iat` not in payload.

- [ ] **Step 3: Add `iat` to `employee_service.authenticate`**

Edit `backend/app/services/employee_service.py`. Replace the existing `payload` dict (around line 69):

```python
    now = datetime.now(UTC)
    payload = {
        "sub": employee.emp_id,
        "role": employee.role.value,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(
            minutes=settings.access_token_expire_minutes,
        ),
    }
```

(`python-jose` accepts `iat` as either an int seconds-since-epoch or a `datetime`. Using int avoids any tz round-trip.)

- [ ] **Step 4: Add `iat` to `authenticate_verify` in the router**

Edit `backend/app/routers/auth.py`. Replace the existing `payload` dict (around line 190):

```python
    now = datetime.now(UTC)
    payload = {
        "sub": employee.emp_id,
        "role": employee.role.value,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(
            minutes=settings.access_token_expire_minutes,
        ),
    }
```

- [ ] **Step 5: Run the test plus the existing test suite**

```bash
pytest tests/unit/test_jwt_iat_claim.py -v
pytest -q
```

Expected: new test passes; all 279+ existing tests still pass (existing tests don't assert anything that contradicts the new claim).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/employee_service.py backend/app/routers/auth.py backend/tests/unit/test_jwt_iat_claim.py
git commit -m "feat(auth): set iat claim on issued JWTs"
```

---

### Task 5: Add `change_password` to `employee_service` (TDD)

**Files:**
- Create: `backend/tests/unit/test_change_password_service.py`
- Modify: `backend/app/services/employee_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/unit/test_change_password_service.py`:

```python
"""Unit tests for employee_service.change_password."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Role
from app.repositories import employee_repository as repo
from app.services import employee_service
from app.utils.password import hash_password, verify_password


async def _make_employee(
    session: AsyncSession,
    emp_id: str = "EMP100",
    password: str = "oldPass1",
    terminated_at: datetime.datetime | None = None,
) -> Employee:
    employee = Employee(
        emp_id=emp_id,
        name="Test",
        department="X",
        role=Role.EMPLOYEE,
        hashed_password=hash_password(password),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
        terminated_at=terminated_at,
    )
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee


@pytest.mark.asyncio
async def test_change_password_success(db_session: AsyncSession) -> None:
    await _make_employee(db_session)

    await employee_service.change_password(
        db_session, "EMP100", current="oldPass1", new="newPass1"
    )

    updated = await repo.find_by_id(db_session, "EMP100")
    assert updated is not None
    assert not verify_password("oldPass1", updated.hashed_password)
    assert verify_password("newPass1", updated.hashed_password)
    assert updated.password_changed_at is not None


@pytest.mark.asyncio
async def test_change_password_wrong_current(db_session: AsyncSession) -> None:
    await _make_employee(db_session)

    with pytest.raises(ValueError, match="Invalid credentials"):
        await employee_service.change_password(
            db_session, "EMP100", current="WRONG", new="newPass1"
        )


@pytest.mark.asyncio
async def test_change_password_unknown_employee(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="Invalid credentials"):
        await employee_service.change_password(
            db_session, "GHOST", current="oldPass1", new="newPass1"
        )


@pytest.mark.asyncio
async def test_change_password_terminated(db_session: AsyncSession) -> None:
    await _make_employee(
        db_session,
        terminated_at=datetime.datetime.now(datetime.UTC),
    )

    with pytest.raises(ValueError, match="Invalid credentials"):
        await employee_service.change_password(
            db_session, "EMP100", current="oldPass1", new="newPass1"
        )


@pytest.mark.asyncio
async def test_change_password_same_as_current(
    db_session: AsyncSession,
) -> None:
    await _make_employee(db_session)

    with pytest.raises(ValueError, match="must differ"):
        await employee_service.change_password(
            db_session, "EMP100", current="oldPass1", new="oldPass1"
        )


@pytest.mark.asyncio
async def test_change_password_same_as_emp_id(db_session: AsyncSession) -> None:
    await _make_employee(db_session, emp_id="EMP100", password="oldPass1")

    with pytest.raises(ValueError, match="must not equal employee ID"):
        await employee_service.change_password(
            db_session, "EMP100", current="oldPass1", new="EMP100"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_change_password_service.py -v
```

Expected: `AttributeError: module 'app.services.employee_service' has no attribute 'change_password'`.

- [ ] **Step 3: Implement `change_password`**

Edit `backend/app/services/employee_service.py`. Add at the bottom:

```python
async def change_password(
    session: AsyncSession,
    emp_id: str,
    current: str,
    new: str,
) -> None:
    """Change an employee's password after verifying the current one.

    Same generic "Invalid credentials" error for not-found / wrong-password /
    terminated, matching the ``authenticate`` pattern (CLAUDE.md decision #4).

    Distinct errors for the two policy violations callers can legitimately
    surface to the user (the JWT already proved who they are):
    - new password equal to current password ("must differ")
    - new password equal to the emp_id ("must not equal employee ID")

    The new password's length / digit policy is enforced by the Pydantic
    schema; this function trusts ``new`` to already satisfy it.

    Raises
    ------
    ValueError
        On any of the conditions above.
    """
    employee = await repo.find_by_id(session, emp_id)
    if employee is None:
        raise ValueError("Invalid credentials")
    if employee.terminated_at is not None:
        raise ValueError("Invalid credentials")
    if not verify_password(current, employee.hashed_password):
        raise ValueError("Invalid credentials")

    if new == current:
        raise ValueError("new password must differ from current password")
    if new == emp_id:
        raise ValueError("new password must not equal employee ID")

    await repo.update_employee(
        session,
        emp_id,
        {
            "hashed_password": hash_password(new),
            "password_changed_at": datetime.now(UTC),
        },
    )
```

(Verify `repo.update_employee` accepts an arbitrary dict — `employee_service.update_employee:118` already calls it that way, so it does.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_change_password_service.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/employee_service.py backend/tests/unit/test_change_password_service.py
git commit -m "feat(backend): add change_password service"
```

---

### Task 6: Enforce `iat ≥ password_changed_at` in middleware (TDD)

**Files:**
- Create: `backend/tests/integration/test_jwt_iat_revocation.py`
- Modify: `backend/app/middleware/auth_middleware.py`

- [ ] **Step 1: Write failing integration tests**

Create `backend/tests/integration/test_jwt_iat_revocation.py`:

```python
"""JWT revocation via password_changed_at vs iat."""

from __future__ import annotations

import datetime
import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Role
from app.utils.password import hash_password


async def _make_emp(
    session: AsyncSession, emp_id: str, pwd: str = "oldPass1"
) -> Employee:
    e = Employee(
        emp_id=emp_id,
        name="Rev",
        department="X",
        role=Role.EMPLOYEE,
        hashed_password=hash_password(pwd),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    session.add(e)
    await session.commit()
    return e


@pytest.mark.asyncio
async def test_old_jwt_rejected_after_password_change(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "REV001")

    # Step 1: get a JWT
    r = await client.post(
        "/api/auth/login", json={"emp_id": "REV001", "password": "oldPass1"}
    )
    assert r.status_code == 200
    old_token = r.json()["access_token"]

    # Step 2: confirm /me works with it
    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert r.status_code == 200

    # Step 3: change password (ensure at least 1 second elapses so iat < now)
    time.sleep(1)
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert r.status_code == 200

    # Step 4: old JWT is now revoked
    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_new_jwt_after_change_still_works(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "REV002")

    r = await client.post(
        "/api/auth/login", json={"emp_id": "REV002", "password": "oldPass1"}
    )
    old_token = r.json()["access_token"]
    time.sleep(1)
    await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {old_token}"},
    )

    # Login again with new password
    r = await client.post(
        "/api/auth/login", json={"emp_id": "REV002", "password": "newPass1"}
    )
    assert r.status_code == 200
    new_token = r.json()["access_token"]

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_legacy_employee_no_password_changed_at_still_works(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An employee created before this feature has password_changed_at = NULL.
    Their existing JWTs must continue to validate.
    """
    await _make_emp(db_session, "REV003")
    # password_changed_at is NULL by default

    r = await client.post(
        "/api/auth/login", json={"emp_id": "REV003", "password": "oldPass1"}
    )
    token = r.json()["access_token"]

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
```

(`client` is the existing async test client fixture; `db_session` matches the existing project DB fixture name. Adapt names if your `conftest.py` uses different ones.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_jwt_iat_revocation.py -v
```

Expected: 404 on `/api/auth/change-password` (endpoint not yet created) — that's fine for now; we'll come back. The shape of the failure we care about is that the middleware doesn't yet revoke. Mark these tests `xfail` temporarily if they block — or skip this step and revisit after Task 7. The simpler path is: implement middleware first (Step 3 below), then come back here.

- [ ] **Step 3: Modify `get_current_user` to enforce the revocation rule**

Edit `backend/app/middleware/auth_middleware.py`. Replace `get_current_user` and add the necessary imports at the top:

```python
import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.employee import Role
from app.repositories import employee_repository
```

Then update the function body:

```python
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Decode and validate a JWT Bearer token.

    Also enforces revocation via ``password_changed_at``: if the token's
    ``iat`` predates the employee's most recent password change, reject.
    Legacy employees with ``password_changed_at IS NULL`` are exempt.

    Returns the token payload dict with at least ``sub`` and ``role``.
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

    # Revocation check
    iat = payload.get("iat")
    if iat is not None:
        employee = await employee_repository.find_by_id(session, payload["sub"])
        if (
            employee is not None
            and employee.password_changed_at is not None
        ):
            iat_dt = datetime.datetime.fromtimestamp(
                iat, tz=datetime.UTC
            )
            if iat_dt < employee.password_changed_at:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    return payload
```

(Tokens without an `iat` — those issued before Task 4 ships — skip the check, preserving backward compatibility.)

- [ ] **Step 4: Run the full test suite — watch for regressions**

```bash
pytest -q
```

Expected: existing tests still pass. Some tests that issue tokens manually without going through `authenticate` may now need to set `iat` to keep going through `/me`; if any fail, update them to mint tokens with `iat` set to current epoch.

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/auth_middleware.py backend/tests/integration/test_jwt_iat_revocation.py
git commit -m "feat(auth): revoke JWTs older than employee.password_changed_at"
```

(The revocation tests in this task's file will fully pass only after Task 7 ships the endpoint they depend on. That's acceptable — we'll re-run them then.)

---

## Phase 3 — Backend API

### Task 7: Add `POST /api/auth/change-password` router endpoint (TDD)

**Files:**
- Create: `backend/tests/integration/test_change_password_endpoint.py`
- Modify: `backend/app/routers/auth.py`

- [ ] **Step 1: Write failing integration tests**

Create `backend/tests/integration/test_change_password_endpoint.py`:

```python
"""Integration tests for POST /api/auth/change-password."""

from __future__ import annotations

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.rate_limiter import clear_all as clear_rate_limit
from app.models.employee import Employee, Role
from app.utils.password import hash_password


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    clear_rate_limit()
    yield
    clear_rate_limit()


async def _login(
    client: AsyncClient, emp_id: str, password: str
) -> str:
    r = await client.post(
        "/api/auth/login", json={"emp_id": emp_id, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _make_emp(
    session: AsyncSession, emp_id: str, pwd: str = "oldPass1"
) -> Employee:
    e = Employee(
        emp_id=emp_id,
        name="CP",
        department="X",
        role=Role.EMPLOYEE,
        hashed_password=hash_password(pwd),
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    session.add(e)
    await session.commit()
    return e


@pytest.mark.asyncio
async def test_change_password_happy_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP001")
    token = await _login(client, "CP001", "oldPass1")

    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["message"]

    # Old password no longer works
    r = await client.post(
        "/api/auth/login", json={"emp_id": "CP001", "password": "oldPass1"}
    )
    assert r.status_code == 401

    # New password works
    r = await client.post(
        "/api/auth/login", json={"emp_id": "CP001", "password": "newPass1"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_wrong_current_password_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP002")
    token = await _login(client, "CP002", "oldPass1")

    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "WRONG", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_no_jwt_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "newPass1"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_weak_new_password_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP003")
    token = await _login(client, "CP003", "oldPass1")

    # Too short
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "short1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422

    # No digit
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "abcdefgh"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_new_equals_current_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP004")
    token = await _login(client, "CP004", "oldPass1")

    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "oldPass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
    assert "differ" in r.json()["detail"]


@pytest.mark.asyncio
async def test_new_equals_emp_id_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "EMP123A")
    token = await _login(client, "EMP123A", "oldPass1")

    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "oldPass1", "new_password": "EMP123A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # "EMP123A" passes schema (8 chars, has digit), so we reach service-layer
    # check
    assert r.status_code == 422
    assert "employee ID" in r.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limit_after_5_wrong_currents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_emp(db_session, "CP005")
    token = await _login(client, "CP005", "oldPass1")

    for _ in range(5):
        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": "WRONG", "new_password": "newPass1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401

    # 6th attempt is rate-limited
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "WRONG", "new_password": "newPass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 429
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_change_password_endpoint.py -v
```

Expected: 404 on every call — the endpoint doesn't exist yet.

- [ ] **Step 3: Implement the router endpoint**

Edit `backend/app/routers/auth.py`. Add to the imports at the top:

```python
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
```

(Merging into the existing import line — `ChangePasswordRequest` joins the existing list.)

Then append a new handler after the existing `/me` handler (around line 52):

```python
@router.post("/change-password", status_code=200)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Change the authenticated user's password. Forces re-login everywhere."""
    emp_id = user["sub"]
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{emp_id}:cp"

    check_rate_limit(rate_limit_key)

    try:
        await employee_service.change_password(
            session, emp_id, body.current_password, body.new_password
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "Invalid credentials":
            record_failed_attempt(rate_limit_key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        # Policy violations (new==current, new==emp_id) — 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=msg,
        )

    reset_rate_limit(rate_limit_key)
    return {"message": "password changed, please log in again"}
```

The rate-limit key suffix `:cp` keeps change-password attempts isolated from login attempts (so failed change attempts don't lock the user out of `/login` and vice versa).

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/integration/test_change_password_endpoint.py -v
pytest tests/integration/test_jwt_iat_revocation.py -v
```

Expected: all change-password and revocation tests pass.

- [ ] **Step 5: Run full backend suite**

```bash
pytest -q
```

Expected: every test passes (existing 279 + new tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/integration/test_change_password_endpoint.py
git commit -m "feat(api): add POST /api/auth/change-password endpoint"
```

---

## Phase 4 — Frontend

> **Before each frontend task:** read `frontend/node_modules/next/dist/docs/` for any topic you touch (per `frontend/AGENTS.md`). The Next.js in this project diverges from public docs.

### Task 8: Add `changePassword.*` i18n keys to en.json and zh.json

**Files:**
- Modify: `frontend/src/messages/en.json`
- Modify: `frontend/src/messages/zh.json`

- [ ] **Step 1: Add the English keys**

Edit `frontend/src/messages/en.json`. Add a new top-level block before the closing `}`:

```json
  "changePassword": {
    "title": "Change Password",
    "subtitle": "Update your account password",
    "currentLabel": "Current password",
    "newLabel": "New password",
    "confirmLabel": "Confirm new password",
    "submit": "Update password",
    "submitting": "Updating...",
    "hint": "At least 8 characters, including a digit",
    "success": "Password updated. Please log in again.",
    "errors": {
      "wrongCurrent": "Current password is incorrect",
      "tooShort": "Password must be at least 8 characters",
      "missingDigit": "Password must contain at least one digit",
      "sameAsCurrent": "New password must differ from current",
      "sameAsEmpId": "New password must not equal your Employee ID",
      "mismatch": "New password and confirmation do not match",
      "rateLimited": "Too many attempts. Please try again later.",
      "generic": "Failed to change password. Please try again."
    }
  }
```

(Insert *before* the file's closing `}` and add a comma at the end of whatever block currently precedes it.)

- [ ] **Step 2: Add the Traditional Chinese keys (繁體中文)**

Edit `frontend/src/messages/zh.json`. Add the parallel block before the closing `}`:

```json
  "changePassword": {
    "title": "變更密碼",
    "subtitle": "更新您的帳戶密碼",
    "currentLabel": "目前密碼",
    "newLabel": "新密碼",
    "confirmLabel": "確認新密碼",
    "submit": "更新密碼",
    "submitting": "更新中...",
    "hint": "至少 8 字元，且包含至少一個數字",
    "success": "密碼已更新，請重新登入",
    "errors": {
      "wrongCurrent": "目前密碼不正確",
      "tooShort": "密碼長度必須至少 8 個字元",
      "missingDigit": "密碼必須包含至少一個數字",
      "sameAsCurrent": "新密碼必須與目前密碼不同",
      "sameAsEmpId": "新密碼不可與員工編號相同",
      "mismatch": "新密碼與確認密碼不相符",
      "rateLimited": "嘗試次數過多，請稍後再試",
      "generic": "密碼變更失敗，請再試一次"
    }
  }
```

- [ ] **Step 3: Verify JSON validity**

```bash
cd frontend
node -e "JSON.parse(require('fs').readFileSync('src/messages/en.json','utf8')); JSON.parse(require('fs').readFileSync('src/messages/zh.json','utf8')); console.log('OK')"
```

Expected: `OK`. If JSON parse fails, fix the trailing comma situation noted in Step 1.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/messages/en.json frontend/src/messages/zh.json
git commit -m "i18n: add changePassword.* keys (en, zh)"
```

---

### Task 9: Add `changePasswordSchema` to validators.ts (TDD)

**Files:**
- Create: `frontend/src/lib/__tests__/changePasswordSchema.test.ts`
- Modify: `frontend/src/lib/validators.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/lib/__tests__/changePasswordSchema.test.ts`:

```typescript
import { describe, expect, it } from "vitest";

import { changePasswordSchema } from "@/lib/validators";

describe("changePasswordSchema", () => {
  const valid = {
    currentPassword: "oldPass1",
    newPassword: "newPass1",
    confirmPassword: "newPass1",
    empId: "EMP001",
  };

  it("accepts a valid payload", () => {
    expect(changePasswordSchema.safeParse(valid).success).toBe(true);
  });

  it("rejects when current password is empty", () => {
    const r = changePasswordSchema.safeParse({ ...valid, currentPassword: "" });
    expect(r.success).toBe(false);
  });

  it("rejects when new password is too short", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      newPassword: "short1",
      confirmPassword: "short1",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("tooShort");
    }
  });

  it("rejects when new password has no digit", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      newPassword: "abcdefgh",
      confirmPassword: "abcdefgh",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("missingDigit");
    }
  });

  it("rejects when confirm doesn't match new", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      confirmPassword: "different1",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("mismatch");
    }
  });

  it("rejects when new password equals current password", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      newPassword: "oldPass1",
      confirmPassword: "oldPass1",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("sameAsCurrent");
    }
  });

  it("rejects when new password equals emp_id", () => {
    const r = changePasswordSchema.safeParse({
      ...valid,
      newPassword: "EMP001",
      confirmPassword: "EMP001",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(JSON.stringify(r.error.issues)).toContain("sameAsEmpId");
    }
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend
npx vitest run src/lib/__tests__/changePasswordSchema.test.ts
```

Expected: module-not-found / `changePasswordSchema` not exported.

- [ ] **Step 3: Implement the schema**

Edit `frontend/src/lib/validators.ts`. Append:

```typescript
export const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, "required"),
    newPassword: z
      .string()
      .min(8, "tooShort")
      .max(128, "tooShort")
      .refine((s) => /\d/.test(s), { message: "missingDigit" }),
    confirmPassword: z.string().min(1, "required"),
    empId: z.string().min(1),
  })
  .refine((d) => d.newPassword === d.confirmPassword, {
    path: ["confirmPassword"],
    message: "mismatch",
  })
  .refine((d) => d.newPassword !== d.currentPassword, {
    path: ["newPassword"],
    message: "sameAsCurrent",
  })
  .refine((d) => d.newPassword !== d.empId, {
    path: ["newPassword"],
    message: "sameAsEmpId",
  });

export type ChangePasswordInput = z.infer<typeof changePasswordSchema>;
```

The message strings are i18n keys (not display text); the form maps them via `t("changePassword.errors.<key>")`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run src/lib/__tests__/changePasswordSchema.test.ts
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/validators.ts frontend/src/lib/__tests__/changePasswordSchema.test.ts
git commit -m "feat(frontend): add changePasswordSchema with i18n-keyed errors"
```

---

### Task 10: Build `ChangePasswordForm` component (TDD)

**Files:**
- Create: `frontend/src/components/__tests__/ChangePasswordForm.test.tsx`
- Create: `frontend/src/components/ChangePasswordForm.tsx`

- [ ] **Step 1: Write failing component tests**

Create `frontend/src/components/__tests__/ChangePasswordForm.test.tsx`:

```typescript
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { ChangePasswordForm } from "@/components/ChangePasswordForm";

// Minimal mocks for the hooks/router/api the component depends on.
const mockPush = vi.fn();
const mockLogout = vi.fn();
const mockPost = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { emp_id: "EMP001", role: "EMPLOYEE" },
    logout: mockLogout,
  }),
}));

vi.mock("@/lib/api", () => ({
  apiClient: { post: (...args: unknown[]) => mockPost(...args) },
  ApiError: class ApiError extends Error {
    constructor(public status: number, public detail: string) {
      super(detail);
    }
  },
}));

// Translation just echoes the key so we can assert on keys.
vi.mock("@/lib/i18n", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

beforeEach(() => {
  mockPush.mockReset();
  mockLogout.mockReset();
  mockPost.mockReset();
});

describe("ChangePasswordForm", () => {
  function fill(current: string, next: string, confirm: string) {
    fireEvent.change(screen.getByLabelText("changePassword.currentLabel"), {
      target: { value: current },
    });
    fireEvent.change(screen.getByLabelText("changePassword.newLabel"), {
      target: { value: next },
    });
    fireEvent.change(screen.getByLabelText("changePassword.confirmLabel"), {
      target: { value: confirm },
    });
  }

  it("disables submit until form is valid", () => {
    render(<ChangePasswordForm />);
    expect(
      screen.getByRole("button", { name: "changePassword.submit" }),
    ).toBeDisabled();
  });

  it("blocks submit when new password lacks a digit", async () => {
    render(<ChangePasswordForm />);
    fill("oldPass1", "abcdefgh", "abcdefgh");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.missingDigit");
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("blocks submit when confirm doesn't match", async () => {
    render(<ChangePasswordForm />);
    fill("oldPass1", "newPass1", "different1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.mismatch");
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("on 200, logs out and redirects to /login", async () => {
    mockPost.mockResolvedValueOnce({ message: "ok" });
    render(<ChangePasswordForm />);
    fill("oldPass1", "newPass1", "newPass1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/auth/change-password", {
        current_password: "oldPass1",
        new_password: "newPass1",
      });
    });
    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("on 401, shows wrongCurrent error", async () => {
    const { ApiError } = await import("@/lib/api");
    mockPost.mockRejectedValueOnce(new ApiError(401, "Invalid credentials"));
    render(<ChangePasswordForm />);
    fill("WRONG_PWD1", "newPass1", "newPass1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.wrongCurrent");
  });

  it("on 422 about emp_id, shows sameAsEmpId error", async () => {
    const { ApiError } = await import("@/lib/api");
    mockPost.mockRejectedValueOnce(
      new ApiError(422, "new password must not equal employee ID"),
    );
    render(<ChangePasswordForm />);
    // pass a value that survives client-side validation: 8+ chars + digit and
    // not literally equal to "EMP001" (client check is strict equality)
    fill("oldPass1", "EMP001x1", "EMP001x1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.sameAsEmpId");
  });

  it("on 429, shows rate-limit error", async () => {
    const { ApiError } = await import("@/lib/api");
    mockPost.mockRejectedValueOnce(new ApiError(429, "too many"));
    render(<ChangePasswordForm />);
    fill("oldPass1", "newPass1", "newPass1");
    fireEvent.click(screen.getByRole("button", { name: "changePassword.submit" }));
    await screen.findByText("changePassword.errors.rateLimited");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend
npx vitest run src/components/__tests__/ChangePasswordForm.test.tsx
```

Expected: import error — `ChangePasswordForm` doesn't exist.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/ChangePasswordForm.tsx`:

```typescript
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock } from "lucide-react";

import { apiClient, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n";
import { changePasswordSchema } from "@/lib/validators";

type FieldErrors = Partial<{
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
  form: string;
}>;

export function ChangePasswordForm() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const router = useRouter();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);

  const empId = user?.emp_id ?? "";

  function validate(): { ok: true } | { ok: false; errors: FieldErrors } {
    const result = changePasswordSchema.safeParse({
      currentPassword: current,
      newPassword: next,
      confirmPassword: confirm,
      empId,
    });
    if (result.success) return { ok: true };
    const fieldErrors: FieldErrors = {};
    for (const issue of result.error.issues) {
      const field = issue.path[0];
      const key = `changePassword.errors.${issue.message}`;
      if (field === "currentPassword" && !fieldErrors.currentPassword) {
        fieldErrors.currentPassword = key;
      } else if (field === "newPassword" && !fieldErrors.newPassword) {
        fieldErrors.newPassword = key;
      } else if (field === "confirmPassword" && !fieldErrors.confirmPassword) {
        fieldErrors.confirmPassword = key;
      }
    }
    return { ok: false, errors: fieldErrors };
  }

  const isValid = current.length > 0 && next.length >= 8 && confirm.length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrors({});
    const v = validate();
    if (!v.ok) {
      setErrors(v.errors);
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post("/api/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      logout();
      router.push("/login");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setErrors({
            currentPassword: "changePassword.errors.wrongCurrent",
          });
        } else if (err.status === 422) {
          const msg = err.detail.toLowerCase();
          if (msg.includes("employee id")) {
            setErrors({ newPassword: "changePassword.errors.sameAsEmpId" });
          } else if (msg.includes("differ")) {
            setErrors({ newPassword: "changePassword.errors.sameAsCurrent" });
          } else if (msg.includes("digit")) {
            setErrors({ newPassword: "changePassword.errors.missingDigit" });
          } else {
            setErrors({ newPassword: "changePassword.errors.tooShort" });
          }
        } else if (err.status === 429) {
          setErrors({ form: "changePassword.errors.rateLimited" });
        } else {
          setErrors({ form: "changePassword.errors.generic" });
        }
      } else {
        setErrors({ form: "changePassword.errors.generic" });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label
          htmlFor="cp-current"
          className="block text-sm font-medium text-gray-700"
        >
          {t("changePassword.currentLabel")}
        </label>
        <input
          id="cp-current"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 shadow-sm focus:border-[#4ec6c1] focus:outline-none"
        />
        {errors.currentPassword && (
          <p className="mt-1 text-sm text-red-600">{t(errors.currentPassword)}</p>
        )}
      </div>

      <div>
        <label
          htmlFor="cp-new"
          className="block text-sm font-medium text-gray-700"
        >
          {t("changePassword.newLabel")}
        </label>
        <input
          id="cp-new"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 shadow-sm focus:border-[#4ec6c1] focus:outline-none"
        />
        <p className="mt-1 text-xs text-gray-500">{t("changePassword.hint")}</p>
        {errors.newPassword && (
          <p className="mt-1 text-sm text-red-600">{t(errors.newPassword)}</p>
        )}
      </div>

      <div>
        <label
          htmlFor="cp-confirm"
          className="block text-sm font-medium text-gray-700"
        >
          {t("changePassword.confirmLabel")}
        </label>
        <input
          id="cp-confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 shadow-sm focus:border-[#4ec6c1] focus:outline-none"
        />
        {errors.confirmPassword && (
          <p className="mt-1 text-sm text-red-600">{t(errors.confirmPassword)}</p>
        )}
      </div>

      {errors.form && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {t(errors.form)}
        </div>
      )}

      <button
        type="submit"
        disabled={!isValid || submitting}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-[#4ec6c1] to-[#6dcf7c] px-4 py-2 text-sm font-medium text-white hover:from-[#45b5b0] hover:to-[#5fc06e] disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Lock className="h-4 w-4" />
        {submitting ? t("changePassword.submitting") : t("changePassword.submit")}
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run src/components/__tests__/ChangePasswordForm.test.tsx
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ChangePasswordForm.tsx frontend/src/components/__tests__/ChangePasswordForm.test.tsx
git commit -m "feat(frontend): add ChangePasswordForm component"
```

---

### Task 11: Create `/dashboard/change-password` page and quick-action card

**Files:**
- Create: `frontend/src/app/dashboard/change-password/page.tsx`
- Modify: `frontend/src/app/dashboard/page.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/src/app/dashboard/change-password/page.tsx`:

```typescript
"use client";

import Link from "next/link";
import { ChevronLeft, Lock } from "lucide-react";

import { ChangePasswordForm } from "@/components/ChangePasswordForm";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useTranslation } from "@/lib/i18n";

export default function ChangePasswordPage() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#e8faf9] via-[#edfbf0] to-[#f5fbe8]">
      <LanguageSwitcher />
      <div className="mx-auto max-w-md px-4 py-8">
        <Link
          href="/dashboard"
          className="mb-6 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-[#4ec6c1]"
        >
          <ChevronLeft className="h-4 w-4" />
          {t("common.backToDashboard")}
        </Link>

        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-[#4ec6c1] to-[#6dcf7c] text-white">
              <Lock className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                {t("changePassword.title")}
              </h1>
              <p className="text-sm text-gray-500">
                {t("changePassword.subtitle")}
              </p>
            </div>
          </div>

          <ChangePasswordForm />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add the quick-action card to the dashboard**

Edit `frontend/src/app/dashboard/page.tsx`. At line 17, add `Lock` to the lucide-react imports:

```typescript
import {
  LayoutDashboard,
  Clock,
  Users,
  Settings,
  FileText,
  CalendarDays,
  Calendar,
  MapPin,
  Fingerprint,
  Check,
  LogOut,
  Lock,
} from "lucide-react";
```

Then inside the `quickActions` grid (after the `monthly-override` `NavLinkCard` around line 328), add:

```tsx
            <NavLinkCard
              href="/dashboard/change-password"
              label={t("changePassword.title")}
              description={t("changePassword.subtitle")}
              icon={<Lock className="h-5 w-5" />}
            />
```

- [ ] **Step 3: Boot the dev stack and smoke-test the route**

```bash
# Terminal A
docker-compose up -d db
cd backend
. .venv/Scripts/activate    # Windows PowerShell: .\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Terminal B
cd frontend
npm run dev
```

Then in a browser at `http://localhost:3000`:
1. Log in.
2. Confirm the new "Change Password / 變更密碼" card appears on the dashboard.
3. Click it; the form renders; both languages render correctly via the LanguageSwitcher.
4. Submit with wrong current password → see localized "Current password is incorrect" inline error.
5. Submit with a valid current + valid new + matching confirm → redirected to `/login`, old token rejected by `/api/auth/me` (verify in Network tab).
6. Log in with new password — succeeds.

- [ ] **Step 4: Run frontend + backend test suites**

```bash
cd frontend && npx vitest run
cd ../backend && pytest -q
```

Expected: all tests pass (68+ frontend, 279+ backend, plus new tests from this feature).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/dashboard/change-password/page.tsx frontend/src/app/dashboard/page.tsx
git commit -m "feat(frontend): add /dashboard/change-password page and quick action"
```

---

## Phase 5 — Verification & Wrap-up

### Task 12: Coverage, lint, and final commit

- [ ] **Step 1: Backend coverage check**

```bash
cd backend
pytest --cov=app --cov-report=term-missing
```

Confirm new code (`employee_service.change_password`, `validate_password_strength`, schemas, router, middleware change) hits ≥80% coverage. Add tests for any uncovered branches before proceeding.

- [ ] **Step 2: Frontend coverage check**

```bash
cd frontend
npx vitest run --coverage
```

Confirm `ChangePasswordForm.tsx`, `changePasswordSchema`, and the page hit ≥80%.

- [ ] **Step 3: Update TODO.md and CLAUDE.md if needed**

Append a new line to `TODO.md` under Phase 14 marking self-service password change as Done. If you decide the JWT-iat invalidation contract deserves a numbered design decision in `CLAUDE.md` (alongside #28), add it as decision #29 with the wording:

> **29. JWT revocation via `password_changed_at`** — On password change, the employee's `password_changed_at` is set to `now(UTC)`. The auth middleware rejects any decoded JWT whose `iat` predates that timestamp. Tokens without an `iat` claim or employees with `password_changed_at IS NULL` skip the check (backward-compat for tokens issued before this feature shipped). Issuance points must set `iat`: `employee_service.authenticate` and `routers/auth.py::authenticate_verify`.

- [ ] **Step 4: Run the full test suite one more time**

```bash
cd backend && pytest -q
cd ../frontend && npx vitest run
```

Expected: green across the board.

- [ ] **Step 5: Push to BOTH remotes**

Per project rule (see `MEMORY.md` `feedback_dual_remote_push.md`): always push to BOTH `origin` (GitHub) and `bitbucket`.

```bash
git push origin main
git push bitbucket main
```

(Adjust branch name if working on a feature branch.)

---

## Self-Review Notes

**Spec coverage check:**
- Data model column: Task 1 ✓
- Endpoint with current-password verification: Task 7 ✓
- Strength policy (8 + digit): Tasks 2, 3 ✓
- Generic 401 for not-found/terminated/wrong: Task 5 service raises a single ValueError("Invalid credentials"); Task 7 router maps to 401 with same body ✓
- JWT revocation via `iat` vs `password_changed_at`: Tasks 4, 6 ✓
- Rate limiting per emp_id: Task 7 (key suffix `:cp`) ✓
- Frontend page + form + Zod + i18n + quick-action: Tasks 8–11 ✓
- Tests at every layer: Tasks 2, 3, 4, 5, 6, 7, 9, 10 ✓
- 422 codes for `new==current` and `new==emp_id`: Task 5 (service raises distinct messages); Task 7 maps non-"Invalid credentials" ValueErrors to 422 ✓
- WebAuthn untouched: no changes to `authenticators` table or WebAuthn flows ✓
- Out of scope (force-change, password history, email reset): not addressed, per spec ✓

**Open-question resolutions from the spec:**
- `iat` issuance: Task 4 adds `iat` to BOTH JWT-issuing paths.
- Rate-limit middleware shape: the existing limiter is in-process (`time.monotonic`, no per-emp_id distinction natively, but the existing login uses `{ip}:{emp_id}` as the key, so we reuse the same pattern with a `:cp` suffix).
- Server error-code wire format: deliberately kept simple — backend returns `{"detail": "<english message>"}` and the frontend matches on substring (`employee id`, `differ`, `digit`) to pick the i18n key. This avoids a one-off error-envelope format; if the project later adopts structured error codes, this is the one place that needs updating.

**Placeholder/ambiguity scan:** no TBDs; every code block is complete; every command shows expected output.

**Type/name consistency:** `password_changed_at` is the column name everywhere; `change_password` is the service function; `ChangePasswordRequest` is the schema; `changePasswordSchema` is the Zod schema; `ChangePasswordForm` is the component; `/api/auth/change-password` is the route. The Zod schema includes an `empId` field that the form fills from `useAuth().user.emp_id`; the backend ignores it (identity comes from JWT).
