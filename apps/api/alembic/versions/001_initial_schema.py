"""Initial schema migration

Revision ID: 001_initial_schema
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create initial tables via SQLAlchemy models
    # This is handled by models.Base.metadata.create_all()
    pass


def downgrade() -> None:
    pass
