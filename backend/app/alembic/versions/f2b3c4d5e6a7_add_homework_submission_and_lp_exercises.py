"""add homework, submission and lessonplan.classroom_exercises

Revision ID: f2b3c4d5e6a7
Revises: i5j6k7l8m9n0
Create Date: 2026-10-26 16:34:00.000000

需求：FR-01/02/03 作业与提交。
- 新增 homework（作业）表与 submission（提交）表
- lessonplan 增加 classroom_exercises（课堂习题，JSON）列，作为「一键生成作业」初始题目来源

P01 修复：改以 i5j6k7l8m9n0 为前驱——organization 表此前从未被任何 revision 创建，
直接建 homework 会因外键引用不存在的表而抛 UndefinedTable（f405）。前驱补齐 organization
等核心表后，本 revision 的外键即可按正常的先建表后引用的顺序建立。

注意：不要给这里的 ForeignKeyConstraint 加 use_alter=True。该标记只对
metadata.create_all() 的拓扑排序生效，alembic 的 op.create_table() 会静默忽略它，
结果是外键一条都不建（实测 homework / organization 上外键为空）。

枚举取值改用与 Python Enum 成员名一致的大写，避免 ORM 写入 'DRAFT' 时
DB 端枚举只有 'draft' 而报 invalid input value for enum。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'f2b3c4d5e6a7'
down_revision = 'i5j6k7l8m9n0'
branch_labels = None
depends_on = None


def _table_exists(connection, name):
    return inspect(connection).has_table(name)


def _column_exists(connection, table, column):
    try:
        cols = [c["name"] for c in inspect(connection).get_columns(table)]
        return column in cols
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    # ---- homework 表 ----
    if not _table_exists(bind, "homework"):
        op.create_table(
            "homework",
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("lesson_plan_id", sa.Uuid(), nullable=True),
            sa.Column("org_id", sa.Uuid(), nullable=True),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("status", sa.Enum("DRAFT", "PUBLISHED", "CLOSED", name="homeworkstatus"), nullable=False),
            sa.Column("knowledge_point_ids", sa.JSON(), nullable=True),
            sa.Column("questions", sa.JSON(), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["lesson_plan_id"], ["lessonplan.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["org_id"], ["organization.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_homework_lesson_plan_id", "homework", ["lesson_plan_id"])
        op.create_index("ix_homework_org_id", "homework", ["org_id"])
        op.create_index("ix_homework_owner_id", "homework", ["owner_id"])

    # ---- submission 表 ----
    if not _table_exists(bind, "submission"):
        op.create_table(
            "submission",
            sa.Column("student_id_hash", sa.String(length=128), nullable=False),
            sa.Column("answers", sa.JSON(), nullable=True),
            sa.Column("status", sa.Enum("SUBMITTED", name="submissionstatus"), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("homework_id", sa.Uuid(), nullable=False),
            sa.Column("org_id", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["homework_id"], ["homework.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["org_id"], ["organization.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_submission_homework_id", "submission", ["homework_id"])
        op.create_index("ix_submission_org_id", "submission", ["org_id"])
        op.create_index("ix_submission_student_id_hash", "submission", ["student_id_hash"])

    # ---- lessonplan.classroom_exercises ----
    if _table_exists(bind, "lessonplan") and not _column_exists(bind, "lessonplan", "classroom_exercises"):
        op.add_column(
            "lessonplan",
            sa.Column("classroom_exercises", sa.JSON(), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    if _table_exists(bind, "submission"):
        op.drop_table("submission")
    if _table_exists(bind, "homework"):
        op.drop_table("homework")
    if _table_exists(bind, "lessonplan") and _column_exists(bind, "lessonplan", "classroom_exercises"):
        op.drop_column("lessonplan", "classroom_exercises")

    # 枚举类型是 CREATE TABLE 时隐式建的，downgrade 只 drop_table 不会带走它们，
    # 残留会让下一次 upgrade 报 "type already exists"，这里显式清理。
    for type_name in ("homeworkstatus", "submissionstatus"):
        try:
            op.execute(f"DROP TYPE IF EXISTS {type_name}")
        except Exception:  # noqa: BLE001
            # 非 PostgreSQL（如 SQLite 开发库）忽略
            pass
