"""add attendance_reasons table

Revision ID: a1b2c3d4e5f6
Revises: 4ade4331a4c7
Create Date: 2026-04-08 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '4ade4331a4c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add attendance_reasons table."""
    op.create_table(
        'attendance_reasons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('summary_id', sa.Integer(), nullable=False),
        sa.Column('emp_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['emp_id'], ['employees.emp_id']),
        sa.ForeignKeyConstraint(['summary_id'], ['daily_attendance_summaries.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('summary_id', name='uq_reason_summary'),
    )


def downgrade() -> None:
    """Remove attendance_reasons table."""
    op.drop_table('attendance_reasons')
