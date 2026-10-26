"""校验 alembic 建出的库结构与 SQLModel.metadata 是否一致。

用途：P01 的验收口径——空白库跑完 `alembic upgrade head` 后，DB 必须与 ORM 元数据
完全对齐（表 / 列 / 外键 / 索引）。可直接挂 CI，不一致时以非零码退出。

用法（连接信息取 POSTGRES_* 环境变量，缺省指向本机 QA 容器）：
    POSTGRES_DB=qa_merge_check python tests/perf/verify_schema.py
    echo $?      # 0 = 一致，1 = 有漂移
"""
import os
import sys

# 让 app 包可导入（脚本位于 backend/tests/perf/）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

os.environ.setdefault("SECRET_KEY", "qa-test-secret-key")

from sqlalchemy import create_engine, inspect  # noqa: E402

from app.models import SQLModel  # noqa: E402

USER = os.environ.get("POSTGRES_USER", "postgres")
PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres123")
HOST = os.environ.get("POSTGRES_SERVER", "localhost")
PORT = os.environ.get("POSTGRES_PORT", "15432")
DB = os.environ.get("POSTGRES_DB", "qa_blank")

URL = f"postgresql+psycopg://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB}"
print("目标库:", f"{HOST}:{PORT}/{DB}")
eng = create_engine(URL)
insp = inspect(eng)

db_tables = set(insp.get_table_names())
meta_tables = set(SQLModel.metadata.tables.keys())

print("DB 表数:", len(db_tables), " metadata 表数:", len(meta_tables))
missing = sorted(meta_tables - db_tables)
print("metadata 有但 DB 缺:", missing if missing else "无")

problems = []
for tname in sorted(meta_tables & db_tables):
    t = SQLModel.metadata.tables[tname]
    db_cols = {c["name"] for c in insp.get_columns(tname)}
    meta_cols = {c.name for c in t.columns}
    if db_cols != meta_cols:
        problems.append(
            f"{tname}: 缺列 {sorted(meta_cols - db_cols)} / 多列 {sorted(db_cols - meta_cols)}"
        )
    db_fks = {(f["constrained_columns"][0], f["referred_table"])
              for f in insp.get_foreign_keys(tname)}
    meta_fks = {(f.parent.name, f.column.table.name) for f in t.foreign_keys}
    if db_fks != meta_fks:
        problems.append(f"{tname}: 外键不一致 db={sorted(db_fks)} meta={sorted(meta_fks)}")

    db_idx = {i["name"] for i in insp.get_indexes(tname)} - {
        c["name"] for c in insp.get_unique_constraints(tname)
    }
    meta_idx = {i.name for i in t.indexes}
    if not meta_idx.issubset(db_idx):
        problems.append(f"{tname}: 缺索引 {sorted(meta_idx - db_idx)}")

fk_total = sum(len(insp.get_foreign_keys(t)) for t in sorted(meta_tables & db_tables))
print("外键总数:", fk_total)

print()
if problems or missing:
    print("【不一致】")
    for p in problems:
        print("  -", p)
    print("\n结论：schema 与 ORM metadata 存在漂移，请检查迁移脚本。")
    sys.exit(1)

print("【一致】所有共有表的列 / 外键 / 索引均与 metadata 匹配")
