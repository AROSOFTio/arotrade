"""manual trading fields

Revision ID: 008_manual_trading_fields
Revises: 007_live_execution_intent_fields
Create Date: 2026-07-13 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008_manual_trading_fields'
down_revision = '007_live_execution_intent_fields'
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return inspector.has_table(table_name) and any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # 1. Alter execution_intents.signal_id to be nullable
    if inspector.has_table("execution_intents"):
        op.alter_column('execution_intents', 'signal_id',
                        existing_type=sa.INTEGER(),
                        nullable=True)
                        
    # 2. Add columns to ai_analyses
    if inspector.has_table("ai_analyses"):
        if not _has_column(inspector, "ai_analyses", "candle_close_time"):
            op.add_column("ai_analyses", sa.Column("candle_close_time", sa.DateTime(), nullable=True))
        if not _has_column(inspector, "ai_analyses", "quote_time"):
            op.add_column("ai_analyses", sa.Column("quote_time", sa.DateTime(), nullable=True))
        if not _has_column(inspector, "ai_analyses", "quote_age_seconds"):
            op.add_column("ai_analyses", sa.Column("quote_age_seconds", sa.Float(), nullable=True))
        if not _has_column(inspector, "ai_analyses", "stale_data_warning"):
            op.add_column("ai_analyses", sa.Column("stale_data_warning", sa.Boolean(), server_default=sa.text("false")))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # 1. Alter execution_intents.signal_id back to not nullable
    if inspector.has_table("execution_intents"):
        op.alter_column('execution_intents', 'signal_id',
                        existing_type=sa.INTEGER(),
                        nullable=False)
                        
    # 2. Drop columns from ai_analyses
    if inspector.has_table("ai_analyses"):
        for col_name in ("stale_data_warning", "quote_age_seconds", "quote_time", "candle_close_time"):
            if _has_column(inspector, "ai_analyses", col_name):
                op.drop_column("ai_analyses", col_name)
