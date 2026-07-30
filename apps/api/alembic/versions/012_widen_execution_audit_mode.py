"""Widen execution audit mode field.

Revision ID: 012_widen_execution_audit_mode
Revises: 011_scope_bridge_keys
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "012_widen_execution_audit_mode"
down_revision = "011_scope_bridge_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "execution_audits",
        "mode",
        existing_type=sa.String(length=10),
        type_=sa.String(length=30),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "execution_audits",
        "mode",
        existing_type=sa.String(length=30),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
