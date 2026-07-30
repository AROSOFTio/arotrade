"""Attach AI analyses to broker accounts.

Revision ID: 010_ai_analysis_broker
Revises: 009_remove_legacy_media
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "010_ai_analysis_broker"
down_revision = "009_remove_legacy_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("ai_analyses"):
        return

    columns = {column["name"] for column in inspector.get_columns("ai_analyses")}
    if "broker_account_id" not in columns:
        op.add_column("ai_analyses", sa.Column("broker_account_id", sa.Integer(), nullable=True))

    inspector = inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("ai_analyses")}
    if "ix_ai_analyses_broker_account_id" not in indexes:
        op.create_index("ix_ai_analyses_broker_account_id", "ai_analyses", ["broker_account_id"])

    foreign_keys = {key["name"] for key in inspector.get_foreign_keys("ai_analyses")}
    if "fk_ai_analyses_broker_account_id" not in foreign_keys and inspector.has_table("broker_accounts"):
        op.create_foreign_key(
            "fk_ai_analyses_broker_account_id",
            "ai_analyses",
            "broker_accounts",
            ["broker_account_id"],
            ["id"],
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("ai_analyses"):
        return

    foreign_keys = {key["name"] for key in inspector.get_foreign_keys("ai_analyses")}
    if "fk_ai_analyses_broker_account_id" in foreign_keys:
        op.drop_constraint("fk_ai_analyses_broker_account_id", "ai_analyses", type_="foreignkey")

    indexes = {index["name"] for index in inspector.get_indexes("ai_analyses")}
    if "ix_ai_analyses_broker_account_id" in indexes:
        op.drop_index("ix_ai_analyses_broker_account_id", table_name="ai_analyses")

    columns = {column["name"] for column in inspector.get_columns("ai_analyses")}
    if "broker_account_id" in columns:
        op.drop_column("ai_analyses", "broker_account_id")
