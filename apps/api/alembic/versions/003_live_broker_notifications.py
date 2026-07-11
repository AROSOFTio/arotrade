"""Add MetaApi broker-account fields and notifications table.

Revision ID: 003_live_broker_notifications
Revises: 002_execution_safety
Create Date: 2026-07-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "003_live_broker_notifications"
down_revision = "002_execution_safety"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("broker_accounts"):
        from app import models
        models.Base.metadata.create_all(bind=bind)
        return

    broker_columns = [
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("server", sa.String(length=100), nullable=True),
        sa.Column("platform", sa.String(length=10), nullable=True),
        sa.Column("metaapi_account_id", sa.String(length=64), nullable=True),
        sa.Column("connection_state", sa.String(length=30), nullable=True),
    ]
    for column in broker_columns:
        if not _has_column(inspector, "broker_accounts", column.name):
            op.add_column("broker_accounts", column)

    inspector = sa.inspect(bind)
    existing_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("broker_accounts")
        if constraint.get("name")
    }
    if "uq_broker_accounts_metaapi_account_id" not in existing_uniques:
        op.create_unique_constraint(
            "uq_broker_accounts_metaapi_account_id", "broker_accounts", ["metaapi_account_id"]
        )

    if not inspector.has_table("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=30), server_default="general"),
            sa.Column("link", sa.String(length=255), nullable=True),
            sa.Column("is_read", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
        op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
        op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("notifications"):
        op.drop_table("notifications")

    if inspector.has_table("broker_accounts"):
        existing_uniques = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("broker_accounts")
            if constraint.get("name")
        }
        if "uq_broker_accounts_metaapi_account_id" in existing_uniques:
            op.drop_constraint("uq_broker_accounts_metaapi_account_id", "broker_accounts", type_="unique")
        for column_name in ("connection_state", "metaapi_account_id", "platform", "server", "name"):
            inspector = sa.inspect(bind)
            if _has_column(inspector, "broker_accounts", column_name):
                op.drop_column("broker_accounts", column_name)
