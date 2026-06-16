"""add reports_to and rank to employees

Phase 15B — org reporting hierarchy. Adds a self-referential reporting edge
(`reports_to`) and a display-only org-chart label (`rank`) to employees.
Both nullable; no backfill (existing rows stay valid, reports_to=NULL = flat
tree that behaves exactly like today until edges are assigned).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-16 15:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("reports_to", sa.String(), nullable=True),
    )
    op.add_column(
        "employees",
        sa.Column("rank", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_employees_reports_to",
        "employees",
        ["reports_to"],
    )
    # Self-referential FK. ON DELETE SET NULL so hard-deleting a manager
    # orphans their reports to the top of the tree rather than blocking the
    # delete or leaving a dangling reference.
    op.create_foreign_key(
        "fk_employees_reports_to_employees",
        "employees",
        "employees",
        ["reports_to"],
        ["emp_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_employees_reports_to_employees",
        "employees",
        type_="foreignkey",
    )
    op.drop_index("ix_employees_reports_to", table_name="employees")
    op.drop_column("employees", "rank")
    op.drop_column("employees", "reports_to")
