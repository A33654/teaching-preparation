"""add candidate knowledge points and extraction logs

Revision ID: b7c3d1e9f0a1
Revises: a4f2b1c9d8e7
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = 'b7c3d1e9f0a1'
down_revision = 'a4f2b1c9d8e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'candidateknowledgepoint',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=100), nullable=False),
        sa.Column('grade_level', sa.String(length=50), nullable=True),
        sa.Column('textbook_version', sa.String(length=200), nullable=True),
        sa.Column('definition', sa.String(length=2000), nullable=True),
        sa.Column('prerequisites', sa.String(length=1000), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=True),
        sa.Column('submitter_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_candidateknowledgepoint_name', 'candidateknowledgepoint', ['name'])
    op.create_index('ix_candidateknowledgepoint_status', 'candidateknowledgepoint', ['status'])
    op.create_index('ix_candidateknowledgepoint_document_id', 'candidateknowledgepoint', ['document_id'])

    op.create_table(
        'extractionlog',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('message', sa.String(length=2000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_extractionlog_task_type', 'extractionlog', ['task_type'])


def downgrade():
    op.drop_table('extractionlog')
    op.drop_table('candidateknowledgepoint')
