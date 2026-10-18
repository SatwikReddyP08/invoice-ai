"""add_review_desk_columns

Revision ID: c57d8123ef01
Revises: 452c29e9aa0d
Create Date: 2026-10-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c57d8123ef01'
down_revision: Union[str, Sequence[str], None] = '452c29e9aa0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema: adds dedicated review desk columns for human reviewer disposition.
    Note: The application also supports storing reviewer dispositions inside review_result JSON,
    allowing immediate zero-downtime execution prior to running this migration.
    Manual execution command: alembic upgrade head
    """
    op.add_column('invoices', sa.Column('review_disposition', sa.String(length=50), nullable=True))
    op.add_column('invoices', sa.Column('reviewer_notes', sa.String(length=1000), nullable=True))
    op.add_column('invoices', sa.Column('disposition_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('invoices', 'disposition_at')
    op.drop_column('invoices', 'reviewer_notes')
    op.drop_column('invoices', 'review_disposition')
