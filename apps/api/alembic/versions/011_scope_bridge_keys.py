"""Scope direct MT5 bridge keys to one broker account.

Revision ID: 011_scope_bridge_keys
Revises: 010_ai_analysis_broker
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "011_scope_bridge_keys"
down_revision = "010_ai_analysis_broker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("api_keys")}
    if "broker_account_id" not in columns:
        op.add_column("api_keys", sa.Column("broker_account_id", sa.Integer(), nullable=True))

    inspector = inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("api_keys")}
    if "ix_api_keys_broker_account_id" not in indexes:
        op.create_index("ix_api_keys_broker_account_id", "api_keys", ["broker_account_id"])

    foreign_keys = {key["name"] for key in inspector.get_foreign_keys("api_keys")}
    if "fk_api_keys_broker_account_id" not in foreign_keys:
        op.create_foreign_key(
            "fk_api_keys_broker_account_id",
            "api_keys",
            "broker_accounts",
            ["broker_account_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    foreign_keys = {key["name"] for key in inspector.get_foreign_keys("api_keys")}
    if "fk_api_keys_broker_account_id" in foreign_keys:
        op.drop_constraint("fk_api_keys_broker_account_id", "api_keys", type_="foreignkey")

    indexes = {index["name"] for index in inspector.get_indexes("api_keys")}
    if "ix_api_keys_broker_account_id" in indexes:
        op.drop_index("ix_api_keys_broker_account_id", table_name="api_keys")

    columns = {column["name"] for column in inspector.get_columns("api_keys")}
    if "broker_account_id" in columns:
        op.drop_column("api_keys", "broker_account_id")
