# Self-Service Password Change — Design Spec

**Date:** 2026-05-13
**Status:** Approved (pending user spec review)
**Phase:** 14 (UX Enhancements)

## Problem

Employees cannot change their own password. The only password-update path is HR-only via `PUT /api/employees/{id}` exposed through the admin panel. Users who want to rotate their password must ask HR — high friction and discourages routine rotation.

## Goals

- Authenticated employees can change their own password through the dashboard.
- A successful change forces re-login on every device (including the current one), preventing stolen JWTs from outliving the rotation.
- Strength policy: minimum 8 characters with at least one digit.
- Same generic error for "wrong current password", "terminated account", and "user not found" — no enumeration leak.
- Existing accounts (before this feature ships) are unaffected: their JWTs continue to work normally.

## Non-Goals

- Force-change-on-first-login flow for HR-provisioned accounts.
- WebAuthn credential revocation on password change (orthogonal factors).
- Password history / "cannot reuse last N passwords".
- "Forgot password" reset via email.
- Account lockout on repeated failed attempts beyond rate limiting.

## High-Level Design

One new authenticated endpoint, `POST /api/auth/change-password`, that:
1. Verifies the current password against the employee identified by the JWT (not by request body).
2. Validates the new password against the strength policy.
3. Writes the new hash plus a `password_changed_at` timestamp.

The auth middleware learns one new rule: reject any JWT whose `iat` (issued-at) predates the employee's `password_changed_at`. Legacy rows where `password_changed_at IS NULL` are exempt, so existing tokens continue to validate.

The frontend gets a `/dashboard/change-password` page reachable from a dashboard quick-action card. On success the client clears its JWT and redirects to `/login`.

## Data Model

**Migration**: add one column to `employees`.

```sql
ALTER TABLE employees ADD COLUMN password_changed_at TIMESTAMPTZ NULL;
```

- Nullable on purpose: existing rows do not need backfill, and `NULL` means "never self-changed" — the middleware treats it as "do not invalidate any prior JWTs for this user".
- No index needed (only read on the per-request employee load, which is already keyed by primary key).

## Backend Components

### Files Touched

```
backend/app/
  models/employee.py              — add password_changed_at column
  schemas/auth.py                 — add ChangePasswordRequest with field_validator
  utils/password.py               — add validate_password_strength(plain) -> None
  services/auth_service.py        — NEW: change_password(session, emp_id, current, new)
  routers/auth.py                 — POST /change-password handler
  middleware/auth.py              — JWT iat-vs-password_changed_at check; ensure iat is set on issue
  alembic/versions/<new>.py       — migration: add password_changed_at column
```

### Request Schema

```python
class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def must_contain_digit(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one digit")
        return v
```

### Service Behavior (`auth_service.change_password`)

1. Load employee by `emp_id` (from JWT).
2. Reject 401 with a single generic message ("Invalid credentials") if any of:
   - employee not found
   - `employee.terminated_at is not None`
   - `verify_password(current, employee.hashed_password)` is `False`
3. Reject 422 if `new_password == current_password` (no-op rotation).
4. Reject 422 if `new_password == emp_id` (trivial password).
5. Write `hashed_password = hash_password(new)` and `password_changed_at = datetime.now(UTC)`.
6. Return nothing; the router responds 200 with a generic message.

The "same generic 401 for not-found / terminated / wrong password" rule matches the existing `authenticate` pattern (CLAUDE.md decision #4).

### Router

```python
@router.post("/change-password", status_code=200)
async def change_password(
    body: ChangePasswordRequest,
    employee: Employee = Depends(get_current_employee),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    await auth_service.change_password(
        session, employee.emp_id, body.current_password, body.new_password
    )
    return {"message": "password changed, please log in again"}
```

The endpoint never accepts an `emp_id` from the request body — the employee identity is always the JWT bearer.

### JWT Invalidation

`create_access_token` must set `iat` explicitly (python-jose does not add it automatically). If the existing implementation does not, we add:

```python
to_encode["iat"] = datetime.now(UTC)
```

In `get_current_employee` (middleware), after decoding the payload and loading the employee:

```python
iat = payload.get("iat")
if employee.password_changed_at is not None and iat is not None:
    iat_dt = datetime.fromtimestamp(iat, tz=UTC)
    if iat_dt < employee.password_changed_at:
        raise HTTPException(401, "token revoked, please log in again")
```

Legacy rows with `password_changed_at IS NULL` skip the check entirely — no regression for existing tokens.

### Rate Limiting

Reuse the existing `middleware/rate_limiting.py` pattern. Default for this endpoint: **5 attempts per 15 minutes, keyed by emp_id**. Exceeding returns 429.

## Frontend Components

### Files Touched

```
frontend/src/
  app/dashboard/change-password/page.tsx     — NEW: the page (server component thin shell)
  app/dashboard/page.tsx                     — add quick-action card linking to it
  components/ChangePasswordForm.tsx          — NEW: client form component
  lib/validators.ts                          — add changePasswordSchema (Zod)
  lib/api-client.ts                          — add changePassword(current, new) call
  messages/en.json                           — add changePassword.* keys
  messages/zh.json                           — add changePassword.* keys (繁體中文)
  types/index.ts                             — add ChangePasswordRequest type if needed
```

### Form

Three masked fields: current password, new password, confirm new password.

Client-side Zod validation mirrors the backend rules so users get inline errors before submit. Backend remains the source of truth and re-validates.

```typescript
export const changePasswordSchema = z.object({
  currentPassword: z.string().min(1),
  newPassword: z
    .string()
    .min(8, "tooShort")
    .max(128)
    .refine((s) => /\d/.test(s), "missingDigit"),
  confirmPassword: z.string(),
}).refine((d) => d.newPassword === d.confirmPassword, {
  path: ["confirmPassword"],
  message: "mismatch",
}).refine((d) => d.newPassword !== d.currentPassword, {
  path: ["newPassword"],
  message: "sameAsCurrent",
});
```

(Error messages are i18n keys, not display strings.)

### Submit Flow

1. POST `/api/auth/change-password` with `{current_password, new_password}`.
2. On **200**: toast success → clear JWT via auth context → `router.push('/login')`.
3. On **401**: inline error on current-password field (`changePassword.errors.wrongCurrent`).
4. On **422**: backend error code is mapped to one of the `changePassword.errors.*` keys (never render raw server English).
5. On **429**: form-level error (`changePassword.errors.rateLimited`).

### Dashboard Entry Point

Add a "變更密碼 / Change Password" card to the existing dashboard quick-actions grid (alongside Monthly Override, Reports, etc.) so the feature is discoverable.

### i18n Keys

Both `en.json` and `zh.json` gain:

```
changePassword.title
changePassword.currentLabel
changePassword.newLabel
changePassword.confirmLabel
changePassword.submit
changePassword.hint                       — "至少 8 字元，且包含至少一個數字"
changePassword.success                    — "密碼已更新，請重新登入"
changePassword.errors.wrongCurrent        — "目前密碼不正確"
changePassword.errors.tooShort
changePassword.errors.missingDigit
changePassword.errors.sameAsCurrent
changePassword.errors.sameAsEmpId
changePassword.errors.mismatch
changePassword.errors.rateLimited         — "嘗試次數過多，請稍後再試"
changePassword.errors.generic
```

## Error Handling

| Condition                              | HTTP | Frontend display                                 |
|----------------------------------------|------|--------------------------------------------------|
| Missing/invalid JWT                    | 401  | Redirect to /login                               |
| Wrong current password                 | 401  | `changePassword.errors.wrongCurrent`             |
| Employee terminated                    | 401  | Same generic 401 (no enumeration)                |
| New password too short / no digit      | 422  | `changePassword.errors.tooShort` / `.missingDigit` |
| New password == current                | 422  | `changePassword.errors.sameAsCurrent`            |
| New password == emp_id                 | 422  | `changePassword.errors.sameAsEmpId`              |
| Confirm doesn't match (client-side)    | n/a  | `changePassword.errors.mismatch`                 |
| Rate limit exceeded                    | 429  | `changePassword.errors.rateLimited`              |
| Anything else                          | 5xx  | `changePassword.errors.generic`                  |

The backend uses a discriminator field (e.g., `{"detail": {"code": "missing_digit"}}`) so the frontend can map to i18n keys without parsing English strings. The exact wire format will be finalized during implementation, matching existing endpoint conventions.

## Testing Strategy

**Backend** — pytest + pytest-asyncio.

*Unit tests* (`backend/tests/unit/`):
- `test_password_validator.py`: 8-char-with-digit passes; <8 chars fails; no-digit fails; 128-char boundary.
- `test_auth_schemas.py`: `ChangePasswordRequest` Pydantic validation cases.
- `test_auth_service_change_password.py`: wrong-current → error; terminated → error (same message); new==current → 422; new==emp_id → 422; success writes new hash + `password_changed_at`; original hash no longer verifies.

*Integration tests* (`backend/tests/integration/`):
- `test_auth_change_password_endpoint.py`:
  - 200 happy path; subsequent password-login with old fails; login with new succeeds.
  - 401 on wrong current, 401 on terminated user, 401 with no JWT.
  - 422 on weak new password, new==current, new==emp_id.
  - 429 after 5 attempts in 15 min for same emp_id.
- `test_jwt_invalidation.py`:
  - JWT@T0 → change @T1>T0 → JWT@T0 now rejected 401.
  - Fresh JWT@T2>T1 works.
  - Legacy employee (`password_changed_at IS NULL`): old JWT still works.

**Frontend** — vitest + testing-library:
- `ChangePasswordForm.test.tsx`: Zod cases (too-short, no-digit, mismatch, same-as-current); on 200 calls `clearAuth()` and routes to /login; on 401/422/429 renders correct i18n key.
- `validators.test.ts`: schema unit tests.

**E2E** (Playwright, optional stub): one happy-path — log in, change password, get redirected, log in again with new password.

**Coverage target**: 80%+ on new code.

## TDD Implementation Order

1. Alembic migration + `password_changed_at` field on model.
2. `validate_password_strength` utility (tests first).
3. `ChangePasswordRequest` schema.
4. `auth_service.change_password` (tests first).
5. Router handler.
6. JWT `iat` issuance + middleware revocation check (tests first).
7. Rate limiting wiring.
8. Frontend `changePasswordSchema` + `ChangePasswordForm` component.
9. `/dashboard/change-password` page + dashboard quick-action link.
10. i18n keys in both locales.

Each step follows RED → GREEN → IMPROVE.

## Risks / Open Questions

- **`iat` claim not currently set.** Need to verify the existing `create_access_token` implementation and add `iat` if missing. If `iat` cannot be reliably set on all currently-issued tokens, the legacy `NULL`-exempt rule still keeps them valid until natural expiry.
- **Rate-limit middleware shape.** Need to verify `middleware/rate_limiting.py` supports per-emp_id keying. If it only supports per-IP, we either extend it or accept per-IP keying for this endpoint as a v1 compromise.
- **Server error-code wire format.** The 422 error-code-to-i18n-key mapping format will be aligned with whatever the existing routers already use, to avoid one-off conventions.

## Out of Scope (Explicit)

- Email-based "forgot password" reset.
- Password history / reuse prevention.
- Force-change-on-first-login.
- WebAuthn credential revocation tied to password change.
- Per-IP account lockout beyond rate limiting.
