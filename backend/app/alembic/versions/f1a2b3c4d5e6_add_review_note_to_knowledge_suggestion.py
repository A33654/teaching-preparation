"""add review_note to knowledge_suggestion

Revision ID: f1a2b3c4d5e6
Revises: e5a1c3d7b9f2
Create Date: 2026-10-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = 'e5a1c3d7b9f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'knowledgesuggestion',
        sa.Column('review_note', sa.String(length=2000), nullable=True),
    )


def downgrade():
    op.drop_column('knowledgesuggestion', 'review_note')
