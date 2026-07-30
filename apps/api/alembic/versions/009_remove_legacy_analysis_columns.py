"""Remove legacy analysis media columns.

Revision ID: 009_remove_legacy_analysis_columns
Revises: 008_manual_trading_fields
Create Date: 2026-07-30
"""

from alembic import op
from sqlalchemy import inspect


revision = "009_remove_legacy_analysis_columns"
down_revision = "008_manual_trading_fields"
branch_labels = None
depends_on = None


def _drop_if_present(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns(table_name)}
    if column_name in columns:
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    _drop_if_present("ai_analyses", "image_" + "url")
    _drop_if_present("journal_entries", "screen" + "shot_url")


def downgrade() -> None:
    pass
