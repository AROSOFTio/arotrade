"""mt5 real data and execution

Revision ID: 006_mt5_real_data_and_execution
Revises: 005_scanner_signal_lifecycle
Create Date: 2026-07-12 15:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_mt5_real_data_and_execution'
down_revision = '005_scanner_signal_lifecycle'
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add columns to trades table
    columns_to_add = [
        ("broker_account_id", sa.Integer(), sa.ForeignKey("broker_accounts.id")),
        ("execution_mode", sa.String(length=20), None),
        ("provider", sa.String(length=50), None),
        ("broker_symbol", sa.String(length=30), None),
        ("execution_intent_id", sa.Integer(), sa.ForeignKey("execution_intents.id")),
        ("broker_position_id", sa.String(length=255), None),
        ("broker_deal_id", sa.String(length=255), None),
        ("requested_price", sa.Float(), None),
        ("actual_fill_price", sa.Float(), None),
        ("requested_volume", sa.Float(), None),
        ("actual_volume", sa.Float(), None),
        ("commission", sa.Float(), None),
        ("swap", sa.Float(), None),
        ("broker_profit", sa.Float(), None),
        ("reconciliation_status", sa.String(length=50), None),
        ("opened_time", sa.DateTime(), None),
        ("closed_time", sa.DateTime(), None),
    ]

    for col_name, col_type, fk in columns_to_add:
        if not _has_column(inspector, "trades", col_name):
            op.add_column("trades", sa.Column(col_name, col_type, nullable=True))
            if fk is not None:
                # Add foreign key constraint
                constraint_name = f"fk_trades_{col_name}"
                target_table = fk.column.table.name
                op.create_foreign_key(
                    constraint_name,
                    source_table="trades",
                    referent_table=target_table,
                    local_cols=[col_name],
                    remote_cols=["id"]
                )

    if not _has_column(inspector, "signals", "execution_mode"):
        op.add_column("signals", sa.Column("execution_mode", sa.String(length=20), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns_to_drop = [
        "closed_time",
        "opened_time",
        "reconciliation_status",
        "broker_profit",
        "swap",
        "commission",
        "actual_volume",
        "requested_volume",
        "actual_fill_price",
        "requested_price",
        "broker_deal_id",
        "broker_position_id",
        "execution_intent_id",
        "broker_symbol",
        "provider",
        "execution_mode",
        "broker_account_id",
    ]

    for col_name in columns_to_drop:
        if _has_column(inspector, "trades", col_name):
            # Drop foreign keys first if any
            if col_name in ("broker_account_id", "execution_intent_id"):
                try:
                    op.drop_constraint(f"fk_trades_{col_name}", "trades", type_="foreignkey")
                except Exception:
                    pass
            op.drop_column("trades", col_name)

    if _has_column(inspector, "signals", "execution_mode"):
        op.drop_column("signals", "execution_mode")
