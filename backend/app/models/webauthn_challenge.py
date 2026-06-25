"""WebAuthn challenge model — short-lived, single-use ceremony challenges.

Persisting the challenge in the database (rather than per-process memory) lets
the two-step WebAuthn flow — generate-options then verify — work across multiple
uvicorn workers: the verify request can land on any worker and still find the
challenge. One pending challenge per employee (upserted on generate-options).
"""

import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class WebAuthnChallenge(SQLModel, table=True):
    """A single pending WebAuthn challenge for an employee."""

    __tablename__ = "webauthn_challenges"

    emp_id: str = Field(primary_key=True, foreign_key="employees.emp_id")
    # base64url-encoded challenge bytes (consistent with credential_id encoding)
    challenge: str = Field(nullable=False)
    created_at: datetime.datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
