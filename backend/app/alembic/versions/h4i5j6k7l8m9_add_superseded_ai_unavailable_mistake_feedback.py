"""add submission.superseded, submissiongrade.ai_unavailable and mistakefeedback table

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-10-26 19:50:00.000000

需求：PRD §7③④、§9 R-2 与 §5.3 埋点留痕。
- submission.superseded：同一学生重复提交以最后一次为准（PRD §7④）
- submissiongrade.ai_unavailable：AI 失败显式标记「转人工」（PRD §7①）
- mistakefeedback：误区回流决策留痕，同时作为重复确认的幂等键（§9 R-2）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "h4i5j6k7l8m9"
down_revision = "g3h4i5j6k7l8"
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

    # ---- submission.superseded（PRD §7④ 重复提交以最后一次为准）----
    if _table_exists(bind, "submission") and not _column_exists(bind, "submission", "superseded"):
        op.add_column(
            "submission",
            sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # ---- submissiongrade.ai_unavailable（PRD §7① AI 不可用，转人工）----
    if _table_exists(bind, "submissiongrade") and not _column_exists(
        bind, "submissiongrade", "ai_unavailable"
    ):
        op.add_column(
            "submissiongrade",
            sa.Column("ai_unavailable", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # ---- mistakefeedback（§9 R-2 回流留痕 + 幂等）----
    if not _table_exists(bind, "mistakefeedback"):
        # 幂等建枚举类型，列上置 create_type=False，避免 CREATE TYPE 被重复执行
        op.execute(
            "DO $$ BEGIN "
            "CREATE TYPE mistakefeedbackstatus AS ENUM ('PENDING', 'CONFIRMED', 'REJECTED'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        op.create_table(
            "mistakefeedback",
            sa.Column("homework_id", sa.Uuid(), nullable=False),
            sa.Column("knowledge_point_id", sa.String(length=128), nullable=False),
            sa.Column("content", sa.String(length=500), nullable=False),
            sa.Column("correction", sa.String(length=500), nullable=False),
            sa.Column("misconception_id", sa.String(length=128), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "PENDING",
                    "CONFIRMED",
                    "REJECTED",
                    name="mistakefeedbackstatus",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("decided_by", sa.Uuid(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.ForeignKeyConstraint(["homework_id"], ["homework.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["decided_by"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_mistakefeedback_homework_id", "mistakefeedback", ["homework_id"])
        op.create_index(
            "ix_mistakefeedback_knowledge_point_id",
            "mistakefeedback",
            ["knowledge_point_id"],
        )


def downgrade():
    bind = op.get_bind()
    if _table_exists(bind, "mistakefeedback"):
        op.drop_index("ix_mistakefeedback_knowledge_point_id", table_name="mistakefeedback")
        op.drop_index("ix_mistakefeedback_homework_id", table_name="mistakefeedback")
        op.drop_table("mistakefeedback")
        try:
            op.execute("DROP TYPE IF EXISTS mistakefeedbackstatus")
        except Exception:
            pass
    if _table_exists(bind, "submissiongrade") and _column_exists(
        bind, "submissiongrade", "ai_unavailable"
    ):
        op.drop_column("submissiongrade", "ai_unavailable")
    if _table_exists(bind, "submission") and _column_exists(bind, "submission", "superseded"):
        op.drop_column("submission", "superseded")
