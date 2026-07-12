"""Scanner profile, signal lifecycle, and execution intent.

Revision ID: 005_scanner_signal_lifecycle
Revises: 004_broker_symbol_mapping
Create Date: 2026-07-12 00:00:00.000000

This migration:
  - Creates scanner_profiles table
  - Extends signals table with broker fields, lifecycle status, fingerprint
  - Creates execution_intents table for idempotent order execution
  - All operations are idempotent (safe to run multiple times)
"""
from alembic import op
import sqlalchemy as sa


revision = "005_scanner_signal_lifecycle"
down_revision = "004_broker_symbol_mapping"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def _has_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(
        c.get("name") == constraint_name
        for c in inspector.get_unique_constraints(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # scanner_profiles table
    # ------------------------------------------------------------------
    if not inspector.has_table("scanner_profiles"):
        op.create_table(
            "scanner_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("broker_account_id", sa.Integer(), sa.ForeignKey("broker_accounts.id"), nullable=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("execution_mode", sa.String(20), nullable=False, server_default="paper"),
            sa.Column("symbols", sa.JSON(), nullable=True),
            sa.Column("timeframes", sa.JSON(), nullable=True),
            sa.Column("active_strategy_ids", sa.JSON(), nullable=True),
            sa.Column("minimum_confidence", sa.Float(), server_default="70.0"),
            sa.Column("minimum_risk_reward", sa.Float(), server_default="1.5"),
            sa.Column("max_spread_points", sa.Float(), nullable=True),
            sa.Column("maximum_signal_age_minutes", sa.Integer(), server_default="240"),
            sa.Column("risk_percent", sa.Float(), server_default="0.5"),
            sa.Column("news_block_before_minutes", sa.Integer(), server_default="30"),
            sa.Column("news_block_after_minutes", sa.Integer(), server_default="30"),
            sa.Column("scan_enabled", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("approval_required", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_scanner_profiles_user_id", "scanner_profiles", ["user_id"])
        op.create_index("ix_scanner_profiles_broker_account_id", "scanner_profiles", ["broker_account_id"])

    # ------------------------------------------------------------------
    # signals table extensions
    # ------------------------------------------------------------------
    signal_columns = [
        ("source", sa.String(20)),
        ("scanner_profile_id", sa.Integer()),
        ("strategy_id", sa.Integer()),
        ("broker_account_id", sa.Integer()),
        ("canonical_symbol", sa.String(30)),
        ("broker_symbol", sa.String(30)),
        ("source_candle_time", sa.DateTime()),
        ("detected_price", sa.Float()),
        ("latest_price", sa.Float()),
        ("lifecycle_status", sa.String(30)),
        ("reasoning", sa.JSON()),
        ("invalidation", sa.Text()),
        ("news_warning", sa.Text()),
        ("fingerprint", sa.String(128)),
        ("blocked_reason", sa.Text()),
        ("approved_action", sa.String(30)),
        ("triggered_at", sa.DateTime()),
        ("execution_started_at", sa.DateTime()),
    ]

    inspector = sa.inspect(bind)
    for col_name, col_type in signal_columns:
        if not _has_column(inspector, "signals", col_name):
            op.add_column("signals", sa.Column(col_name, col_type, nullable=True))

    # Make entry_min and entry_max nullable (they can be null for auto signals in progress)
    # This is a PostgreSQL-specific ALTER; safe to skip if already nullable
    try:
        op.alter_column("signals", "entry_min", nullable=True)
        op.alter_column("signals", "entry_max", nullable=True)
        op.alter_column("signals", "stop_loss", nullable=True)
    except Exception:
        pass  # Already nullable — ignore

    # Add scanner_profile_id FK
    inspector = sa.inspect(bind)
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("signals") if fk.get("name")}
    if "fk_signals_scanner_profile_id" not in existing_fks:
        try:
            op.create_foreign_key(
                "fk_signals_scanner_profile_id",
                "signals", "scanner_profiles",
                ["scanner_profile_id"], ["id"],
                ondelete="SET NULL",
            )
        except Exception:
            pass  # May already exist or column not present yet

    # Fingerprint unique constraint
    inspector = sa.inspect(bind)
    if not _has_constraint(inspector, "signals", "uq_signal_fingerprint"):
        try:
            op.create_unique_constraint("uq_signal_fingerprint", "signals", ["fingerprint"])
        except Exception:
            pass  # Already exists

    # Fingerprint index
    if not _has_index(inspector, "signals", "ix_signals_fingerprint"):
        op.create_index("ix_signals_fingerprint", "signals", ["fingerprint"])

    # ------------------------------------------------------------------
    # execution_intents table
    # ------------------------------------------------------------------
    if not inspector.has_table("execution_intents"):
        op.create_table(
            "execution_intents",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signals.id"), nullable=False),
            sa.Column("broker_account_id", sa.Integer(), sa.ForeignKey("broker_accounts.id"), nullable=True),
            sa.Column("execution_mode", sa.String(20), nullable=False),
            sa.Column("client_order_id", sa.String(64), nullable=False),
            sa.Column("requested_volume", sa.Float(), nullable=True),
            sa.Column("requested_price", sa.Float(), nullable=True),
            sa.Column("equity_at_time", sa.Float(), nullable=True),
            sa.Column("risk_percent_at_time", sa.Float(), nullable=True),
            sa.Column("tick_size_at_time", sa.Float(), nullable=True),
            sa.Column("tick_value_at_time", sa.Float(), nullable=True),
            sa.Column("stop_loss_distance", sa.Float(), nullable=True),
            sa.Column("loss_per_lot", sa.Float(), nullable=True),
            sa.Column("raw_volume", sa.Float(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
            sa.Column("broker_order_id", sa.String(255), nullable=True),
            sa.Column("broker_position_id", sa.String(255), nullable=True),
            sa.Column("request_payload", sa.JSON(), nullable=True),
            sa.Column("broker_response", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_intents_signal_id", "execution_intents", ["signal_id"])
        op.create_unique_constraint("uq_client_order_id", "execution_intents", ["client_order_id"])
        op.create_unique_constraint(
            "uq_one_active_intent_per_signal_mode",
            "execution_intents",
            ["signal_id", "execution_mode"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("execution_intents"):
        op.drop_table("execution_intents")

    # Remove signal extensions
    signal_columns_to_drop = [
        "source", "scanner_profile_id", "strategy_id", "broker_account_id",
        "canonical_symbol", "broker_symbol", "source_candle_time",
        "detected_price", "latest_price", "lifecycle_status",
        "reasoning", "invalidation", "news_warning", "fingerprint",
        "blocked_reason", "approved_action", "triggered_at", "execution_started_at",
    ]
    inspector = sa.inspect(bind)
    for col_name in signal_columns_to_drop:
        if _has_column(inspector, "signals", col_name):
            op.drop_column("signals", col_name)

    if inspector.has_table("scanner_profiles"):
        op.drop_table("scanner_profiles")
