"""Attach AI analyses to broker accounts.

Revision ID: 010_add_ai_analysis_broker_account
Revises: 009_remove_legacy_analysis_columns
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "010_add_ai_analysis_broker_account"
down_revision = "009_remove_legacy_analysis_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_analyses", sa.Column("broker_account_id", sa.Integer(), nullable=True))
    op.create_index("ix_ai_analyses_broker_account_id", "ai_analyses", ["broker_account_id"])
    op.create_foreign_key(
        "fk_ai_analyses_broker_account_id",
        "ai_analyses",
        "broker_accounts",
        ["broker_account_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_ai_analyses_broker_account_id", "ai_analyses", type_="foreignkey")
    op.drop_index("ix_ai_analyses_broker_account_id", table_name="ai_analyses")
    op.drop_column("ai_analyses", "broker_account_id")