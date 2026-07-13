"""live execution intent fields

Revision ID: 007_live_execution_intent_fields
Revises: 006_mt5_real_data_and_execution
Create Date: 2026-07-13 16:35:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "007_live_execution_intent_fields"
down_revision = "006_mt5_real_data_and_execution"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return inspector.has_table(table_name) and any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def _unique_constraint_names(inspector, table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("execution_intents"):
        return

    columns = [
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("execution_state", sa.String(length=30), nullable=True),
        sa.Column("broker_deal_id", sa.String(length=255), nullable=True),
        sa.Column("broker_deal_ids", sa.JSON(), nullable=True),
    ]
    for column in columns:
        if not _has_column(inspector, "execution_intents", column.name):
            op.add_column("execution_intents", column)

    inspector = sa.inspect(bind)
    if "uq_execution_intents_idempotency_key" not in _unique_constraint_names(inspector, "execution_intents"):
        op.create_unique_constraint(
            "uq_execution_intents_idempotency_key",
            "execution_intents",
            ["idempotency_key"],
        )

    op.execute("UPDATE execution_intents SET execution_state = status WHERE execution_state IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("execution_intents"):
        return

    if "uq_execution_intents_idempotency_key" in _unique_constraint_names(inspector, "execution_intents"):
        op.drop_constraint("uq_execution_intents_idempotency_key", "execution_intents", type_="unique")

    for column_name in ("broker_deal_ids", "broker_deal_id", "execution_state", "idempotency_key"):
        inspector = sa.inspect(bind)
        if _has_column(inspector, "execution_intents", column_name):
            op.drop_column("execution_intents", column_name)