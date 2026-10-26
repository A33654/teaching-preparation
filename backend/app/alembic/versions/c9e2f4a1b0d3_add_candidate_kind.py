"""add kind/target_kp_id/suggestion to candidate knowledge points

Revision ID: c9e2f4a1b0d3
Revises: b7c3d1e9f0a1
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

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

    # 模型层 kind 带 index=True，原迁移漏建该索引，补齐（幂等，重复执行不报错）
    bind = op.get_bind()
    existing = {i["name"] for i in inspect(bind).get_indexes('candidateknowledgepoint')}
    if 'ix_candidateknowledgepoint_kind' not in existing:
        op.create_index(
            'ix_candidateknowledgepoint_kind', 'candidateknowledgepoint', ['kind']
        )


def downgrade():
    bind = op.get_bind()
    existing = {i["name"] for i in inspect(bind).get_indexes('candidateknowledgepoint')}
    if 'ix_candidateknowledgepoint_kind' in existing:
        op.drop_index('ix_candidateknowledgepoint_kind', table_name='candidateknowledgepoint')
    op.drop_column('candidateknowledgepoint', 'suggestion')
    op.drop_column('candidateknowledgepoint', 'target_kp_id')
    op.drop_column('candidateknowledgepoint', 'kind')
