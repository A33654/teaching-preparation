"""add submissiongrade table, graded_at column, and 'graded' submission status

Revision ID: g3h4i5j6k7l8
Revises: f2b3c4d5e6a7
Create Date: 2026-10-26 17:30:00.000000

需求：FR-04/05/06 判分与批改。
- 新增 submissiongrade（每题判分记录，一题一行）
- submission 增加 graded_at（自动判分完成时间）
- submissionstatus 枚举补充 'graded'
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "g3h4i5j6k7l8"
down_revision = "f2b3c4d5e6a7"
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

    # ---- submission 增加 graded_at ----
    if _table_exists(bind, "submission") and not _column_exists(bind, "submission", "graded_at"):
        op.add_column(
            "submission",
            sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ---- submissionstatus 枚举补充 'graded' ----
    try:
        op.execute("ALTER TYPE submissionstatus ADD VALUE IF NOT EXISTS 'GRADED'")
    except Exception:
        # 非 PostgreSQL（如 SQLite 开发库）忽略
        pass

    # ---- submissiongrade 表 ----
    if not _table_exists(bind, "submissiongrade"):
        op.create_table(
            "submissiongrade",
            sa.Column("submission_id", sa.Uuid(), nullable=False),
            sa.Column("question_id", sa.String(length=64), nullable=False),
            sa.Column(
                "question_type",
                sa.Enum("CHOICE", "FILL", "SHORT", "ESSAY", name="questiontype"),
                nullable=False,
            ),
            sa.Column("full_score", sa.Float(), nullable=False),
            sa.Column("is_correct", sa.Boolean(), nullable=True),
            sa.Column("auto_score", sa.Float(), nullable=True),
            sa.Column("auto_detail", sa.Text(), nullable=True),
            sa.Column("ai_suggested_score", sa.Float(), nullable=True),
            sa.Column("ai_comment", sa.Text(), nullable=True),
            sa.Column("ai_knowledge_points", sa.JSON(), nullable=True),
            sa.Column("ai_confidence", sa.Float(), nullable=True),
            sa.Column("needs_human", sa.Boolean(), nullable=False),
            sa.Column("final_score", sa.Float(), nullable=True),
            sa.Column("final_comment", sa.Text(), nullable=True),
            sa.Column("finalized", sa.Boolean(), nullable=False),
            sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "status",
                sa.Enum("PENDING", "AUTO_GRADED", "FINALIZED", name="questiongradestatus"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.ForeignKeyConstraint(
                ["submission_id"], ["submission.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_submissiongrade_submission_id", "submissiongrade", ["submission_id"]
        )
        op.create_index(
            "ix_submissiongrade_question_id", "submissiongrade", ["question_id"]
        )


def downgrade():
    bind = op.get_bind()
    if _table_exists(bind, "submissiongrade"):
        op.drop_index("ix_submissiongrade_question_id", table_name="submissiongrade")
        op.drop_index("ix_submissiongrade_submission_id", table_name="submissiongrade")
        op.drop_table("submissiongrade")
    if _table_exists(bind, "submission") and _column_exists(bind, "submission", "graded_at"):
        op.drop_column("submission", "graded_at")

    # 同上：清理 CREATE TABLE 时隐式建的枚举类型，否则再次 upgrade 会报类型已存在
    for type_name in ("questiongradestatus", "questiontype"):
        try:
            op.execute(f"DROP TYPE IF EXISTS {type_name}")
        except Exception:  # noqa: BLE001
            pass
