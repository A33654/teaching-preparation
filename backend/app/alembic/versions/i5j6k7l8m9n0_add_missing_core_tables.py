"""add missing core tables (organization / RBAC / ACL / review / contribution / template)

Revision ID: i5j6k7l8m9n0
Revises: f1a2b3c4d5e6
Create Date: 2026-10-26 20:35:00.000000

背景：P01 —— 全新空库执行 `alembic upgrade head` 时，f2b3c4d5e6a7 建 homework 表
因外键引用 organization 而报 UndefinedTable（SQLAlchemy f405）。根因并非单纯建表
顺序：organization / role / permission / resourceacl 等 10 张核心表在整条迁移链中
从未被任何 revision 创建过，此前只能靠 SQLModel.metadata.create_all() 绕过。

本 revision 补齐这 10 张表，并顺带补上 user / lessonplan 上几列从未被迁移过的字段
（org_id / group_id / status / visibility / source_type / version / template_id），
否则全新库虽然能建出来，运行时仍会因缺列报错。

关于「外键后置」的实现方式（重要）：
    SQLAlchemy 的 ForeignKeyConstraint(use_alter=True) 只对 metadata.create_all() 的
    拓扑排序生效；alembic 的 op.create_table() 会**静默忽略**该标记，导致外键根本不会
    被创建（实测：homework / organization 上一条外键都没有）。因此这里用 alembic 原生
    支持的后置方式——先 CREATE TABLE，再统一用 op.create_foreign_key() 追加外键，
    效果等价于 ALTER TABLE ADD CONSTRAINT，且能保证迁移拓扑顺序不被外键依赖卡死。

枚举类型先以幂等 DO 块创建，列上置 create_type=False，避免同一类型被 CREATE TYPE 两次
（gradelevel 由更早的 revision 建好，其余为本 revision 新增）。

本 revision 只建表加列，不动业务代码与模型。已有库（由 create_all 建出）同样带有这些
表和列，故每个动作都用 _table_exists / _column_exists / _index_exists / _fk_exists 做
幂等保护，重复执行不会报错。
"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "i5j6k7l8m9n0"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


# 本 revision 需要的枚举类型（名称 -> 取值，取值与 Python Enum 的成员名一致）
ENUMS = {
    "orgtype": ["SCHOOL", "REGION"],
    "resourcetype": ["LESSON_PLAN", "TEMPLATE", "KNOWLEDGE_ITEM"],
    "granteetype": ["USER", "GROUP", "SCHOOL", "REGION"],
    "aclpermission": ["VIEW", "EDIT"],
    "reviewaction": ["SUBMIT", "APPROVE", "REJECT", "RESUBMIT", "ARCHIVE", "PUBLISH_KB"],
    "contributiontype": ["CREATE", "SUBMIT", "APPROVE", "REFERENCE", "COMMENT"],
    "visibility": ["PRIVATE", "GROUP", "SCHOOL", "REGION", "PUBLIC"],
    "lessonplanstatus": ["DRAFT", "PENDING", "APPROVED", "REJECTED", "ARCHIVED"],
    "lessonplansource": ["PERSONAL", "COLLECTIVE", "KNOWLEDGE_BASE"],
    "gradelevel": ["PRIMARY", "JUNIOR", "SENIOR"],
}

# 后置外键：(表, 列, 引用表.列, ondelete)
FOREIGN_KEYS = [
    ("organization", "parent_id", "organization", "id", "SET NULL"),
    ("role", "org_id", "organization", "id", "CASCADE"),
    ("userrole", "user_id", "user", "id", "CASCADE"),
    ("userrole", "role_id", "role", "id", "CASCADE"),
    ("rolepermission", "role_id", "role", "id", "CASCADE"),
    ("rolepermission", "permission_id", "permission", "id", "CASCADE"),
    ("resourceacl", "org_id", "organization", "id", "CASCADE"),
    ("resourceacl", "created_by", "user", "id", None),
    ("reviewrecord", "org_id", "organization", "id", "CASCADE"),
    ("reviewrecord", "reviewer_id", "user", "id", None),
    ("contributionevent", "user_id", "user", "id", "CASCADE"),
    ("contributionevent", "org_id", "organization", "id", "CASCADE"),
    ("lessonplantemplate", "org_id", "organization", "id", "CASCADE"),
    ("lessonplantemplate", "owner_id", "user", "id", "CASCADE"),
    ("lessonplantemplate", "subject_id", "subject", "id", "SET NULL"),
    ("lessonplanversionsnapshot", "lesson_plan_id", "lessonplan", "id", "CASCADE"),
    ("lessonplanversionsnapshot", "org_id", "organization", "id", "CASCADE"),
    # 本 revision 补建的列所带的外键
    ("user", "org_id", "organization", "id", "SET NULL"),
    ("lessonplan", "org_id", "organization", "id", "CASCADE"),
    ("lessonplan", "template_id", "lessonplantemplate", "id", "SET NULL"),
]

# 本 revision 补建的列：(表, 列名, 类型构造, 是否非空, server_default)
ADDED_COLUMNS = [
    ("user", "org_id", lambda: sa.Uuid(), False, None),
    ("user", "group_id", lambda: sa.Uuid(), False, None),
    ("lessonplan", "org_id", lambda: sa.Uuid(), False, None),
    ("lessonplan", "group_id", lambda: sa.Uuid(), False, None),
    ("lessonplan", "template_id", lambda: sa.Uuid(), False, None),
    ("lessonplan", "version", lambda: sa.Integer(), True, "1"),
    ("lessonplan", "visibility", lambda: _enum("visibility"), True, "PRIVATE"),
    ("lessonplan", "status", lambda: _enum("lessonplanstatus"), True, "DRAFT"),
    ("lessonplan", "source_type", lambda: _enum("lessonplansource"), True, "PERSONAL"),
]

ADDED_INDEXES = [
    ("ix_user_org_id", "user", ["org_id"]),
    ("ix_user_group_id", "user", ["group_id"]),
    ("ix_lessonplan_org_id", "lessonplan", ["org_id"]),
    ("ix_lessonplan_group_id", "lessonplan", ["group_id"]),
]


def _table_exists(connection, name):
    return inspect(connection).has_table(name)


def _column_exists(connection, table, column):
    if not _table_exists(connection, table):
        return False
    return column in {c["name"] for c in inspect(connection).get_columns(table)}


def _index_exists(connection, table, index_name):
    if not _table_exists(connection, table):
        return False
    return index_name in {i["name"] for i in inspect(connection).get_indexes(table)}


def _fk_exists(connection, table, column, ref_table):
    if not _table_exists(connection, table):
        return False
    for fk in inspect(connection).get_foreign_keys(table):
        if column in fk["constrained_columns"] and fk["referred_table"] == ref_table:
            return True
    return False


def _enum(name):
    """构造与 SQLModel.metadata 一致的 Enum 列类型。

    create_type=False：类型已由 _ensure_enums 建好，避免同一类型被 CREATE TYPE 两次。
    """
    return sa.Enum(*ENUMS[name], name=name, create_type=False)


def _ensure_enums():
    """幂等创建枚举类型：已存在则跳过（gradelevel 由更早 revision 建好）。"""
    for name, values in ENUMS.items():
        vals = ", ".join("'" + v + "'" for v in values)
        op.execute(
            f"DO $$ BEGIN "
            f"CREATE TYPE {name} AS ENUM ({vals}); "
            f"EXCEPTION WHEN duplicate_object THEN NULL; "
            f"END $$;"
        )


def _add_foreign_keys(bind):
    """后置外键：先建表，再统一 ALTER 追加，避免建表拓扑被依赖卡死。"""
    for table, col, ref_table, ref_col, ondelete in FOREIGN_KEYS:
        if not _table_exists(bind, table) or not _table_exists(bind, ref_table):
            continue
        if _fk_exists(bind, table, col, ref_table):
            continue
        op.create_foreign_key(
            f"{table}_{col}_fkey",
            table,
            ref_table,
            [col],
            [ref_col],
            ondelete=ondelete,
        )


def upgrade():
    bind = op.get_bind()
    _ensure_enums()

    # ============ 1) 建表（不含外键，外键统一在第 3 步后置追��）============

    if not _table_exists(bind, "organization"):
        op.create_table(
            "organization",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
            sa.Column("type", _enum("orgtype"), nullable=False),
            sa.Column("parent_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_organization_name", "organization", ["name"])

    if not _table_exists(bind, "permission"):
        op.create_table(
            "permission",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
            sa.Column("description", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_permission_code", "permission", ["code"])

    if not _table_exists(bind, "role"):
        op.create_table(
            "role",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
            sa.Column("description", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
            sa.Column("org_id", sa.Uuid(), nullable=True),
            sa.Column("is_system", sa.Boolean(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_role_code", "role", ["code"])

    if not _table_exists(bind, "userrole"):
        op.create_table(
            "userrole",
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("role_id", sa.Uuid(), nullable=False),
            sa.PrimaryKeyConstraint("user_id", "role_id"),
        )

    if not _table_exists(bind, "rolepermission"):
        op.create_table(
            "rolepermission",
            sa.Column("role_id", sa.Uuid(), nullable=False),
            sa.Column("permission_id", sa.Uuid(), nullable=False),
            sa.PrimaryKeyConstraint("role_id", "permission_id"),
        )

    if not _table_exists(bind, "resourceacl"):
        op.create_table(
            "resourceacl",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("org_id", sa.Uuid(), nullable=False),
            sa.Column("resource_type", _enum("resourcetype"), nullable=False),
            sa.Column("resource_id", sa.Uuid(), nullable=False),
            sa.Column("grantee_type", _enum("granteetype"), nullable=False),
            sa.Column("grantee_id", sa.Uuid(), nullable=False),
            sa.Column("permission", _enum("aclpermission"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_resourceacl_grantee_id", "resourceacl", ["grantee_id"])
        op.create_index("ix_resourceacl_resource_id", "resourceacl", ["resource_id"])

    if not _table_exists(bind, "reviewrecord"):
        op.create_table(
            "reviewrecord",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("org_id", sa.Uuid(), nullable=False),
            sa.Column("resource_type", _enum("resourcetype"), nullable=False),
            sa.Column("resource_id", sa.Uuid(), nullable=False),
            sa.Column("reviewer_id", sa.Uuid(), nullable=False),
            sa.Column("action", _enum("reviewaction"), nullable=False),
            sa.Column("from_status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
            sa.Column("to_status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
            sa.Column("comment", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_reviewrecord_resource_id", "reviewrecord", ["resource_id"])

    if not _table_exists(bind, "contributionevent"):
        op.create_table(
            "contributionevent",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("org_id", sa.Uuid(), nullable=False),
            sa.Column("event_type", _enum("contributiontype"), nullable=False),
            sa.Column("resource_type", _enum("resourcetype"), nullable=True),
            sa.Column("resource_id", sa.Uuid(), nullable=True),
            sa.Column("points", sa.Integer(), nullable=False),
            sa.Column("period", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
            sa.Column("dedupe_key", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_contributionevent_dedupe_key", "contributionevent", ["dedupe_key"])
        op.create_index("ix_contributionevent_event_type", "contributionevent", ["event_type"])
        op.create_index("ix_contributionevent_period", "contributionevent", ["period"])
        op.create_index("ix_contributionevent_resource_id", "contributionevent", ["resource_id"])
        op.create_index("ix_contributionevent_user_id", "contributionevent", ["user_id"])

    if not _table_exists(bind, "lessonplantemplate"):
        op.create_table(
            "lessonplantemplate",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("org_id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("grade_level", _enum("gradelevel"), nullable=True),
            sa.Column(
                "teaching_objectives", sqlmodel.sql.sqltypes.AutoString(length=None), nullable=True
            ),
            sa.Column(
                "teaching_process", sqlmodel.sql.sqltypes.AutoString(length=None), nullable=True
            ),
            sa.Column("subject_id", sa.Uuid(), nullable=True),
            sa.Column("visibility", _enum("visibility"), nullable=False),
            sa.Column("status", _enum("lessonplanstatus"), nullable=False),
            sa.Column("source_type", _enum("lessonplansource"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_lessonplantemplate_org_id", "lessonplantemplate", ["org_id"])

    if not _table_exists(bind, "lessonplanversionsnapshot"):
        op.create_table(
            "lessonplanversionsnapshot",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("lesson_plan_id", sa.Uuid(), nullable=False),
            sa.Column("org_id", sa.Uuid(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("snapshot_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_lessonplanversionsnapshot_lesson_plan_id",
            "lessonplanversionsnapshot",
            ["lesson_plan_id"],
        )

    # ============ 2) 补 user / lessonplan 上从未被迁移过的列 ============

    for table, col, type_fn, not_null, default in ADDED_COLUMNS:
        if not _column_exists(bind, table, col):
            op.add_column(
                table,
                sa.Column(
                    col,
                    type_fn(),
                    nullable=not not_null,
                    server_default=default,
                ),
            )
            # NOT NULL 列靠 server_default 兼容已有行，建完即去掉默认值，
            # 避免后续写入沿用迁移期的默认（默认值应由模型层给出）
            if default is not None:
                op.alter_column(table, col, server_default=None)

    for idx_name, table, cols in ADDED_INDEXES:
        if not _index_exists(bind, table, idx_name):
            op.create_index(idx_name, table, cols)

    # ============ 3) 后置外键 ============
    _add_foreign_keys(bind)


def downgrade():
    bind = op.get_bind()

    # 先摘外键（表被 drop 时会自动摘掉，显式处理只为可重复执行）
    for table, col, ref_table, _ref_col, _ondelete in FOREIGN_KEYS:
        if _table_exists(bind, table) and _fk_exists(bind, table, col, ref_table):
            op.drop_constraint(f"{table}_{col}_fkey", table, type_="foreignkey")

    for idx_name, table, _cols in ADDED_INDEXES:
        if _table_exists(bind, table) and _index_exists(bind, table, idx_name):
            op.drop_index(idx_name, table_name=table)

    for table, col, _type_fn, _not_null, _default in ADDED_COLUMNS:
        if _column_exists(bind, table, col):
            op.drop_column(table, col)

    for name in (
        "lessonplanversionsnapshot",
        "lessonplantemplate",
        "contributionevent",
        "reviewrecord",
        "resourceacl",
        "rolepermission",
        "userrole",
        "role",
        "permission",
        "organization",
    ):
        if _table_exists(bind, name):
            op.drop_table(name)
