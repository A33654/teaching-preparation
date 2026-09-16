"""add kind/target_kp_id/suggestion to candidate knowledge points

Revision ID: c9e2f4a1b0d3
Revises: b7c3d1e9f0a1
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


revision = 'c9e2f4a1b0d3'
down_revision = 'b7c3d1e9f0a1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('candidateknowledgepoint', sa.Column('kind', sa.String(length=50), nullable=True))
    op.add_column('candidateknowledgepoint', sa.Column('target_kp_id', sa.String(length=64), nullable=True))
    op.add_column('candidateknowledgepoint', sa.Column('suggestion', sa.String(length=2000), nullable=True))
    # 存量数据默认 llm_extraction
    op.execute("UPDATE candidateknowledgepoint SET kind='llm_extraction' WHERE kind IS NULL")


def downgrade():
    op.drop_column('candidateknowledgepoint', 'suggestion')
    op.drop_column('candidateknowledgepoint', 'target_kp_id')
    op.drop_column('candidateknowledgepoint', 'kind')
