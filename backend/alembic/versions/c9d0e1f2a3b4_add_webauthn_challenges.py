"""add webauthn_challenges table

Persists the WebAuthn ceremony challenge in the database instead of
per-process memory, so the generate-options and verify requests can be served
by different uvicorn workers and still agree on the challenge. One row per
employee; challenges are single-use (deleted on verify) and short-lived.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-25 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webauthn_challenges",
        sa.Column("emp_id", sa.String(), nullable=False),
        sa.Column("challenge", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["emp_id"], ["employees.emp_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("emp_id"),
    )


def downgrade() -> None:
    op.drop_table("webauthn_challenges")
