"""move knowledge graph from postgres to neo4j

知识点与关系迁移到 Neo4j（app/knowledge_graph/），
PostgreSQL 仅保留 knowledge_point_ids 引用。

!!! 升级前请先运行数据迁移脚本（可选，若需保留旧数据）:
    python scripts/migrate_kgs_to_neo4j.py
    然后: alembic upgrade head

Revision ID: a4f2b1c9d8e7
Revises: c22120f31b13
Create Date: 2026-09-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4f2b1c9d8e7'
down_revision = 'c22120f31b13'
branch_labels = None
depends_on = None


def upgrade():
    # 1. 新增知识点 ID 引用列（JSON 数组，指向 Neo4j 节点）
    op.add_column('document', sa.Column('knowledge_point_ids', sa.JSON(), nullable=True))
    op.add_column('document', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('lessonplan', sa.Column('knowledge_point_ids', sa.JSON(), nullable=True))

    # 2. 把 M2M 关联表数据回填到 JSON 列（Neo4j 节点 ID 已在
    #    scripts/migrate_kgs_to_neo4j.py 中保留为原 UUID）
    op.execute("""
        UPDATE lessonplan lp SET knowledge_point_ids = (
            SELECT COALESCE(json_agg(l.knowledge_point_id::text), '[]'::json)
            FROM lessonplanknowledgepointlink l WHERE l.lesson_plan_id = lp.id
        )
    """)
    op.execute("""
        UPDATE document d SET knowledge_point_ids = (
            SELECT COALESCE(json_agg(l.knowledge_point_id::text), '[]'::json)
            FROM documentknowledgepointlink l WHERE l.document_id = d.id
        )
    """)

    # 3. 断开 chapter -> knowledgepoint 外键（列保留，指向 Neo4j 节点 ID）
    try:
        op.drop_constraint('chapter_knowledge_point_id_fkey', 'chapter', type_='foreignkey')
    except Exception:
        pass  # 约束不存在时忽略（兼容不同命名）

    # 4. 删除知识图谱相关表（图谱数据已迁移至 Neo4j）
    op.drop_table('documentknowledgepointlink')
    op.drop_table('lessonplanknowledgepointlink')
    op.drop_table('knowledgerelation')
    op.drop_table('knowledgepoint')


def downgrade():
    # 恢复 PostgreSQL 知识图谱表（M2M 数据从 JSON 列反填，Neo4j 图谱数据不动）
    op.create_table(
        'knowledgepoint',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=2000), nullable=True),
        sa.Column('subject', sa.String(length=100), nullable=False),
        sa.Column('grade_level', sa.String(length=100), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'knowledgerelation',
        sa.Column('relation_type', sa.String(length=50), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['knowledgepoint.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_id'], ['knowledgepoint.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'lessonplanknowledgepointlink',
        sa.Column('lesson_plan_id', sa.Uuid(), nullable=False),
        sa.Column('knowledge_point_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['knowledge_point_id'], ['knowledgepoint.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lesson_plan_id'], ['lessonplan.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('lesson_plan_id', 'knowledge_point_id'),
    )
    op.create_table(
        'documentknowledgepointlink',
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('knowledge_point_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['knowledge_point_id'], ['knowledgepoint.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['document.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('document_id', 'knowledge_point_id'),
    )
    op.create_foreign_key(
        'chapter_knowledge_point_id_fkey',
        'chapter',
        'knowledgepoint',
        ['knowledge_point_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # JSON 列 → M2M 表反填（尽力而为，仅引用仍存在的知识点）
    op.execute("""
        INSERT INTO lessonplanknowledgepointlink (lesson_plan_id, knowledge_point_id)
        SELECT lp.id, kp_id::uuid
        FROM lessonplan lp, json_array_elements_text(
            COALESCE(lp.knowledge_point_ids, '[]'::json)) AS kp_id
        WHERE kp_id::uuid IN (SELECT id FROM knowledgepoint)
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO documentknowledgepointlink (document_id, knowledge_point_id)
        SELECT d.id, kp_id::uuid
        FROM document d, json_array_elements_text(
            COALESCE(d.knowledge_point_ids, '[]'::json)) AS kp_id
        WHERE kp_id::uuid IN (SELECT id FROM knowledgepoint)
        ON CONFLICT DO NOTHING
    """)

    op.drop_column('lessonplan', 'knowledge_point_ids')
    op.drop_column('document', 'summary')
    op.drop_column('document', 'knowledge_point_ids')
