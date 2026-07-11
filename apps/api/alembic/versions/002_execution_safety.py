"""Add auditable execution fields and signal expiry support.

Revision ID: 002_execution_safety
Revises: 001_initial_schema
Create Date: 2026-07-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "002_execution_safety"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _unique_constraint_names(inspector, table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # The original migration intentionally delegated initial table creation to
    # SQLAlchemy. Preserve that compatibility for a new empty database.
    if not inspector.has_table("signals"):
        from app import models
        models.Base.metadata.create_all(bind=bind)
        return

    if not _has_column(inspector, "signals", "valid_until"):
        op.add_column("signals", sa.Column("valid_until", sa.DateTime(), nullable=True))

    trade_columns = [
        sa.Column("broker", sa.String(length=50), nullable=True),
        sa.Column("broker_order_id", sa.String(length=255), nullable=True),
        sa.Column("client_order_id", sa.String(length=255), nullable=True),
        sa.Column("execution_status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("execution_error", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("filled_at", sa.DateTime(), nullable=True),
    ]
    for column in trade_columns:
        if not _has_column(inspector, "trades", column.name):
            op.add_column("trades", column)

    inspector = sa.inspect(bind)
    existing_unique_constraints = _unique_constraint_names(inspector, "trades")
    if "uq_trades_broker_order_id" not in existing_unique_constraints:
        op.create_unique_constraint("uq_trades_broker_order_id", "trades", ["broker_order_id"])
    if "uq_trades_client_order_id" not in existing_unique_constraints:
        op.create_unique_constraint("uq_trades_client_order_id", "trades", ["client_order_id"])

    if not inspector.has_table("execution_audits"):
        op.create_table(
            "execution_audits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signals.id"), nullable=True),
            sa.Column("trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=True),
            sa.Column("broker", sa.String(length=50), nullable=False),
            sa.Column("mode", sa.String(length=10), nullable=False),
            sa.Column("outcome", sa.String(length=30), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_audits_user_id", "execution_audits", ["user_id"])
        op.create_index("ix_execution_audits_signal_id", "execution_audits", ["signal_id"])
        op.create_index("ix_execution_audits_trade_id", "execution_audits", ["trade_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("execution_audits"):
        op.drop_table("execution_audits")

    if inspector.has_table("trades"):
        existing_unique_constraints = _unique_constraint_names(inspector, "trades")
        if "uq_trades_client_order_id" in existing_unique_constraints:
            op.drop_constraint("uq_trades_client_order_id", "trades", type_="unique")
        if "uq_trades_broker_order_id" in existing_unique_constraints:
            op.drop_constraint("uq_trades_broker_order_id", "trades", type_="unique")

        for column_name in (
            "filled_at",
            "submitted_at",
            "execution_error",
            "execution_status",
            "client_order_id",
            "broker_order_id",
            "broker",
        ):
            inspector = sa.inspect(bind)
            if _has_column(inspector, "trades", column_name):
                op.drop_column("trades", column_name)

    inspector = sa.inspect(bind)
    if inspector.has_table("signals") and _has_column(inspector, "signals", "valid_until"):
        op.drop_column("signals", "valid_until")
