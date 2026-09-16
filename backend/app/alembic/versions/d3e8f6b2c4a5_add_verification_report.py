"""add verification_report to lessonplan

Revision ID: d3e8f6b2c4a5
Revises: c9e2f4a1b0d3
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e8f6b2c4a5'
down_revision = 'c9e2f4a1b0d3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('lessonplan', sa.Column('verification_report', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('lessonplan', 'verification_report')
