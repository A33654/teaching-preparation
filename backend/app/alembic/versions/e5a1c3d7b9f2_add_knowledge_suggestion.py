"""add knowledge_suggestion table

Revision ID: e5a1c3d7b9f2
Revises: d3e8f6b2c4a5
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5a1c3d7b9f2'
down_revision = 'd3e8f6b2c4a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'knowledgesuggestion',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=100), nullable=False),
        sa.Column('grade_level', sa.String(length=50), nullable=True),
        sa.Column('textbook_version', sa.String(length=200), nullable=True),
        sa.Column('chapter', sa.String(length=255), nullable=True),
        sa.Column('target_kp_id', sa.String(length=64), nullable=True),
        sa.Column('definition', sa.String(length=2000), nullable=True),
        sa.Column('suggestion', sa.String(length=2000), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('submitter_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_knowledgesuggestion_kind', 'knowledgesuggestion', ['kind'])
    op.create_index('ix_knowledgesuggestion_status', 'knowledgesuggestion', ['status'])


def downgrade():
    op.drop_table('knowledgesuggestion')
