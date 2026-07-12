"""Add broker symbol mapping table and broker account MetaApi fields.

Revision ID: 004_broker_symbol_mapping
Revises: 003_live_broker_notifications
Create Date: 2026-07-12 00:00:00.000000

This migration:
  - Creates the broker_symbols table (canonical → broker symbol mapping)
  - Is idempotent: all operations check whether the object already exists
"""
from alembic import op
import sqlalchemy as sa


revision = "004_broker_symbol_mapping"
down_revision = "003_live_broker_notifications"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # broker_symbols table
    # ------------------------------------------------------------------
    if not inspector.has_table("broker_symbols"):
        op.create_table(
            "broker_symbols",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("broker_account_id", sa.Integer(), sa.ForeignKey("broker_accounts.id"), nullable=False),
            sa.Column("canonical_symbol", sa.String(30), nullable=False),
            sa.Column("broker_symbol", sa.String(30), nullable=False),
            sa.Column("display_name", sa.String(100), nullable=True),
            sa.Column("category", sa.String(30), nullable=True),
            sa.Column("digits", sa.Integer(), nullable=True),
            sa.Column("point", sa.Float(), nullable=True),
            sa.Column("tick_size", sa.Float(), nullable=True),
            sa.Column("tick_value", sa.Float(), nullable=True),
            sa.Column("contract_size", sa.Float(), nullable=True),
            sa.Column("volume_min", sa.Float(), nullable=True),
            sa.Column("volume_max", sa.Float(), nullable=True),
            sa.Column("volume_step", sa.Float(), nullable=True),
            sa.Column("trade_allowed", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("last_refreshed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    # Indexes
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("broker_symbols")} if inspector.has_table("broker_symbols") else set()
    if "ix_broker_symbols_id" not in existing_indexes:
        op.create_index("ix_broker_symbols_id", "broker_symbols", ["id"])
    if "ix_broker_symbols_broker_account_id" not in existing_indexes:
        op.create_index("ix_broker_symbols_broker_account_id", "broker_symbols", ["broker_account_id"])
    if "ix_broker_symbols_canonical_symbol" not in existing_indexes:
        op.create_index("ix_broker_symbols_canonical_symbol", "broker_symbols", ["canonical_symbol"])
    if "ix_broker_symbol_lookup" not in existing_indexes:
        op.create_index("ix_broker_symbol_lookup", "broker_symbols", ["broker_account_id", "canonical_symbol"])

    # Unique constraint
    inspector2 = sa.inspect(bind)
    if inspector2.has_table("broker_symbols"):
        existing_uniques = {c["name"] for c in inspector2.get_unique_constraints("broker_symbols") if c.get("name")}
        if "uq_broker_symbol_per_account" not in existing_uniques:
            op.create_unique_constraint(
                "uq_broker_symbol_per_account", "broker_symbols",
                ["broker_account_id", "broker_symbol"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("broker_symbols"):
        op.drop_table("broker_symbols")
