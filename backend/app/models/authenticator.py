"""Authenticator model for WebAuthn credentials."""

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Authenticator(SQLModel, table=True):
    """Authenticators table — WebAuthn public-key credentials per employee."""

    __tablename__ = "authenticators"

    credential_id: str = Field(primary_key=True)
    emp_id: str = Field(foreign_key="employees.emp_id")
    public_key: bytes = Field(sa_column=sa.Column(sa.LargeBinary, nullable=False))
    sign_count: int = Field(default=0)
