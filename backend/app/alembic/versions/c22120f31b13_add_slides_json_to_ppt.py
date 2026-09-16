"""add slides_json to ppt

Revision ID: c22120f31b13
Revises: ceb6418db698
Create Date: 2026-06-27 21:17:24.701792

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = 'c22120f31b13'
down_revision = 'ceb6418db698'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pptrecord', sa.Column('extracted_text', sa.String(), nullable=True))
    op.add_column('pptrecord', sa.Column('slides_json', sa.String(), nullable=True))
    op.add_column('pptrecord', sa.Column('style', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('pptrecord', 'style')
    op.drop_column('pptrecord', 'slides_json')
    op.drop_column('pptrecord', 'extracted_text')
