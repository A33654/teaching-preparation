# P0 阻塞问题最小修复：diff + 验证命令 + 运行结果

日期：2026-10-26 · 范围：仅迁移脚本 / 哈希配置 / runner 环境判断 · 未改动业务逻辑、模型、已有测试用例

---

## 0. 变更文件清单

| # | 文件 | 类型 | 对应问题 |
|---|------|------|---------|
| 1 | `backend/app/alembic/versions/i5j6k7l8m9n0_add_missing_core_tables.py` | 新增 | P01 |
| 2 | `backend/app/alembic/versions/f2b3c4d5e6a7_add_homework_submission_and_lp_exercises.py` | 修改 | P01 |
| 3 | `backend/app/alembic/versions/g3h4i5j6k7l8_add_submission_grade_and_graded_at.py` | 修改 | P01 |
| 4 | `backend/app/alembic/versions/h4i5j6k7l8m9_add_superseded_ai_unavailable_mistake_feedback.py` | 修改 | P01 |
| 5 | `backend/app/alembic/versions/c9e2f4a1b0d3_add_candidate_kind.py` | 修改 | P01（顺带补齐漏建索引） |
| 6 | `backend/app/core/config.py` | 修改 | P02 |
| 7 | `backend/app/core/security.py` | 修改 | P02 |
| 8 | `backend/tests/platform/runner.py` | 修改 runner 环境判断 | 次要 4 |
| 9 | `backend/tests/perf/verify_schema.py` `backend/tests/perf/verify_hash.py` | 新增校验脚本 | 验证工具 |

---

## 1. P01：全新空库 `alembic upgrade head`

### 1.1 根因（与原判断的差异）

原判断是「建表顺序不合理、外键没有后置创建」。实测下来真实根因是：

```
sqlalchemy.exc.ProgrammingError: (psycopg.errors.UndefinedTable)
relation "organization" does not exist
[SQL: CREATE TABLE homework ( ... FOREIGN KEY(org_id) REFERENCES organization (id) ...)]
```

`organization` 表**在整条迁移链里从未被任何 revision 创建过**。用 metadata 与迁移链做全量比对后，缺口是 10 张表：

```
organization / permission / role / userrole / rolepermission /
resourceacl / reviewrecord / contributionevent /
lessonplantemplate / lessonplanversionsnapshot
```

另外还有两处会同样让部署后应用起不来的问题：

- **表名不一致**：迁移建的是 `submission_grade` / `mistake_feedback`，而 ORM metadata 里是 `submissiongrade` / `mistakefeedback`（SQLModel 默认表名 = 类名小写）。
- **枚举取值口径不一致**：迁移写的是 `('draft','published','closed')`，而 SQLAlchemy 持久化的是 Python Enum 的**成员名** `('DRAFT','PUBLISHED','CLOSED')`。不改的话 ORM 写入 `DRAFT` 会撞 `invalid input value for enum`。

### 1.2 关于 `use_alter=True` 的重要结论

先按原方案给外键加了 `use_alter=True`，在空白库上跑通了，但一校验发现**外键一条都没建出来**：

```
$ psql -c "\d homework"      # 没有任何 FOREIGN KEY
$ psql -c "\d organization"  # 没有任何 FOREIGN KEY
```

原因：`use_alter` 只对 `metadata.create_all()` 的拓扑排序生效，**alembic 的 `op.create_table()` 会静默忽略该标记**——外键既不在 `CREATE TABLE` 里，也不会被补发 `ALTER`，等于被丢弃。这是很危险的静默失败。

所以改为 alembic 原生支持的后置方式：**先 `CREATE TABLE`（不带外键），再统一 `op.create_foreign_key()` 追加**，等价于 `ALTER TABLE ADD CONSTRAINT`，且能保证拓扑顺序不被依赖卡死。效果与「先建表后追加外键」的设计意图一致。

### 1.3 diff — 新增 `i5j6k7l8m9n0_add_missing_core_tables.py`

```diff
+revision = "i5j6k7l8m9n0"
+down_revision = "f1a2b3c4d5e6"     # 插在 homework 之前，先补齐被依赖的表
+
+# 本 revision 需要的枚举类型（取值与 Python Enum 的成员名一致）
+ENUMS = {
+    "orgtype": ["SCHOOL", "REGION"],
+    "resourcetype": ["LESSON_PLAN", "TEMPLATE", "KNOWLEDGE_ITEM"],
+    "granteetype": ["USER", "GROUP", "SCHOOL", "REGION"],
+    "aclpermission": ["VIEW", "EDIT"],
+    "reviewaction": ["SUBMIT", "APPROVE", "REJECT", "RESUBMIT", "ARCHIVE", "PUBLISH_KB"],
+    "contributiontype": ["CREATE", "SUBMIT", "APPROVE", "REFERENCE", "COMMENT"],
+    "visibility": ["PRIVATE", "GROUP", "SCHOOL", "REGION", "PUBLIC"],
+    "lessonplanstatus": ["DRAFT", "PENDING", "APPROVED", "REJECTED", "ARCHIVED"],
+    "lessonplansource": ["PERSONAL", "COLLECTIVE", "KNOWLEDGE_BASE"],
+    "gradelevel": ["PRIMARY", "JUNIOR", "SENIOR"],
+}
+
+# 后置外键：(表, 列, 引用表, 引用列, ondelete) —— 共 20 条
+FOREIGN_KEYS = [
+    ("organization", "parent_id", "organization", "id", "SET NULL"),
+    ("role", "org_id", "organization", "id", "CASCADE"),
+    ("userrole", "user_id", "user", "id", "CASCADE"),
+    ("userrole", "role_id", "role", "id", "CASCADE"),
+    ("rolepermission", "role_id", "role", "id", "CASCADE"),
+    ("rolepermission", "permission_id", "permission", "id", "CASCADE"),
+    ("resourceacl", "org_id", "organization", "id", "CASCADE"),
+    ("resourceacl", "created_by", "user", "id", None),
+    ("reviewrecord", "org_id", "organization", "id", "CASCADE"),
+    ("reviewrecord", "reviewer_id", "user", "id", None),
+    ("contributionevent", "user_id", "user", "id", "CASCADE"),
+    ("contributionevent", "org_id", "organization", "id", "CASCADE"),
+    ("lessonplantemplate", "org_id", "organization", "id", "CASCADE"),
+    ("lessonplantemplate", "owner_id", "user", "id", "CASCADE"),
+    ("lessonplantemplate", "subject_id", "subject", "id", "SET NULL"),
+    ("lessonplanversionsnapshot", "lesson_plan_id", "lessonplan", "id", "CASCADE"),
+    ("lessonplanversionsnapshot", "org_id", "organization", "id", "CASCADE"),
+    ("user", "org_id", "organization", "id", "SET NULL"),
+    ("lessonplan", "org_id", "organization", "id", "CASCADE"),
+    ("lessonplan", "template_id", "lessonplantemplate", "id", "SET NULL"),
+]
+
+# 顺带补齐 user / lessonplan 上从未被迁移过的列
+ADDED_COLUMNS = [
+    ("user", "org_id", ..., False, None),
+    ("user", "group_id", ..., False, None),
+    ("lessonplan", "org_id", ..., False, None),
+    ("lessonplan", "group_id", ..., False, None),
+    ("lessonplan", "template_id", ..., False, None),
+    ("lessonplan", "version", sa.Integer(), True, "1"),
+    ("lessonplan", "visibility", Enum("visibility"), True, "PRIVATE"),
+    ("lessonplan", "status", Enum("lessonplanstatus"), True, "DRAFT"),
+    ("lessonplan", "source_type", Enum("lessonplansource"), True, "PERSONAL"),
+]
+
+def _ensure_enums():
+    """幂等创建枚举类型：已存在则跳过（gradelevel 由更早 revision 建好）。"""
+    for name, values in ENUMS.items():
+        op.execute(f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({vals}); "
+                   f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
+
+def _enum(name):
+    return sa.Enum(*ENUMS[name], name=name, create_type=False)  # 避免重复 CREATE TYPE
+
+def _add_foreign_keys(bind):
+    """后置外键：先建表，再统一 ALTER 追加。"""
+    for table, col, ref_table, ref_col, ondelete in FOREIGN_KEYS:
+        if _table_exists(bind, table) and _table_exists(bind, ref_table) \
+           and not _fk_exists(bind, table, col, ref_table):
+            op.create_foreign_key(f"{table}_{col}_fkey", table, ref_table,
+                                  [col], [ref_col], ondelete=ondelete)
+
+def upgrade():
+    _ensure_enums()
+    # 1) 建 10 张表（不含外键约束）
+    # 2) 补 user / lessonplan 缺失列（NOT NULL 列先带 server_default 再 alter_column 去掉）
+    # 3) _add_foreign_keys(bind)  ← 统一后置追加外键
```

字段与 `SQLModel.metadata` 逐一对应（由 metadata 直接生成，非手抄），保证迁移产出的 schema 与 ORM 期望一致。

### 1.4 diff — `f2b3c4d5e6a7`

```diff
-revision = 'f2b3c4d5e6a7'
-down_revision = 'f1a2b3c4d5e6'
+down_revision = 'i5j6k7l8m9n0'          # 前驱补齐 organization 等核心表

-            sa.Column("status", sa.Enum("draft", "published", "closed", name="homeworkstatus"), nullable=False),
+            sa.Column("status", sa.Enum("DRAFT", "PUBLISHED", "CLOSED", name="homeworkstatus"), nullable=False),

-            sa.Column("status", sa.Enum("submitted", name="submissionstatus"), nullable=False),
+            sa.Column("status", sa.Enum("SUBMITTED", name="submissionstatus"), nullable=False),

 def downgrade():
     ...
+    # 枚举类型是 CREATE TABLE 时隐式建的，downgrade 只 drop_table 不会带走它们，
+    # 残留会让下一次 upgrade 报 "type already exists"，这里显式清理。
+    for type_name in ("homeworkstatus", "submissionstatus"):
+        try:
+            op.execute(f"DROP TYPE IF EXISTS {type_name}")
+        except Exception:  # noqa: BLE001
+            pass
```

### 1.5 diff — `g3h4i5j6k7l8`

```diff
-- 新增 submission_grade（每题判分记录，一题一行）
+- 新增 submissiongrade（每题判分记录，一题一行）      # 表名对齐 ORM metadata（全文件替换）

-    if not _table_exists(bind, "submission_grade"):
+    if not _table_exists(bind, "submissiongrade"):
-        op.create_table("submission_grade", ...)
+        op.create_table("submissiongrade", ...)
-        op.create_index("ix_submission_grade_submission_id", "submission_grade", [...])
+        op.create_index("ix_submissiongrade_submission_id", "submissiongrade", [...])

-                sa.Enum("choice", "fill", "short", "essay", name="questiontype"),
+                sa.Enum("CHOICE", "FILL", "SHORT", "ESSAY", name="questiontype"),
-                sa.Enum("pending", "auto_graded", "finalized", name="questiongradestatus"),
+                sa.Enum("PENDING", "AUTO_GRADED", "FINALIZED", name="questiongradestatus"),

-        op.execute("ALTER TYPE submissionstatus ADD VALUE IF NOT EXISTS 'graded'")
+        op.execute("ALTER TYPE submissionstatus ADD VALUE IF NOT EXISTS 'GRADED'")

+    # 清理 CREATE TABLE 时隐式建的枚举类型，否则再次 upgrade 会报类型已存在
+    for type_name in ("questiongradestatus", "questiontype"):
+        try:
+            op.execute(f"DROP TYPE IF EXISTS {type_name}")
+        except Exception:  # noqa: BLE001
+            pass
```

### 1.6 diff — `h4i5j6k7l8m9`

```diff
-mistake_feedback  →  mistakefeedback        # 表名对齐 ORM metadata（全文件替换）
-submission_grade  →  submissiongrade        # 同上（此前漏改，导致 ai_unavailable 列没加上）

-        try:
-            op.execute("CREATE TYPE mistakefeedbackstatus AS ENUM ('pending', 'confirmed', 'rejected')")
-        except Exception:
-            pass
+        # 幂等建枚举类型，列上置 create_type=False，避免 CREATE TYPE 被重复执行
+        op.execute("DO $$ BEGIN "
+                   "CREATE TYPE mistakefeedbackstatus AS ENUM ('PENDING', 'CONFIRMED', 'REJECTED'); "
+                   "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

-                sa.Enum("pending", "confirmed", "rejected", name="mistakefeedbackstatus"),
+                sa.Enum("PENDING", "CONFIRMED", "REJECTED",
+                        name="mistakefeedbackstatus", create_type=False),
```

### 1.7 diff — `c9e2f4a1b0d3`（顺带补齐漏建索引）

```diff
 import sqlalchemy as sa
 from alembic import op
+from sqlalchemy import inspect

     op.execute("UPDATE candidateknowledgepoint SET kind='llm_extraction' WHERE kind IS NULL")
+    # 模型层 kind 带 index=True，原迁移漏建该索引，补齐（幂等，重复执行不报错）
+    bind = op.get_bind()
+    existing = {i["name"] for i in inspect(bind).get_indexes('candidateknowledgepoint')}
+    if 'ix_candidateknowledgepoint_kind' not in existing:
+        op.create_index('ix_candidateknowledgepoint_kind', 'candidateknowledgepoint', ['kind'])

 def downgrade():
+    bind = op.get_bind()
+    existing = {i["name"] for i in inspect(bind).get_indexes('candidateknowledgepoint')}
+    if 'ix_candidateknowledgepoint_kind' in existing:
+        op.drop_index('ix_candidateknowledgepoint_kind', table_name='candidateknowledgepoint')
     op.drop_column('candidateknowledgepoint', 'suggestion')
```

---

## 2. P02：argon2 哈希成本

### 2.1 diff — `backend/app/core/config.py`

```diff
     NEO4J_DATABASE: str = "neo4j"

+    # ---- 密码哈希（Argon2id）成本参数 ----
+    # P02：默认 time_cost=3 / memory_cost=65536(64MiB) 下单次哈希约 110ms，
+    # 登录并发时因内存带宽争抢放大到 P50 619ms。这里下调为
+    # time_cost=2 / memory_cost=32768(32MiB)，单次哈希约 36ms，
+    # 仍高于 OWASP 建议下限（m=19MiB, t=2），属于安全与性能的折中。
+    # 注意：仅影响「新写入」的密码哈希；已存哈希自带参数，校验照旧可用，无需重置用户密码。
+    ARGON2_TIME_COST: int = 2
+    ARGON2_MEMORY_COST: int = 32768  # 单位 KiB
```

### 2.2 diff — `backend/app/core/security.py`

```diff
-password_hash = PasswordHash(
-    (
-        Argon2Hasher(),
-        BcryptHasher(),
-    )
-)
+# P02：Argon2id 成本参数由 settings 下发，便于按环境调整而无需改代码。
+# 已存的哈希自带参数，下调成本不会让老密码失效（校验仍按原参数进行）。
+password_hash = PasswordHash(
+    (
+        Argon2Hasher(
+            time_cost=settings.ARGON2_TIME_COST,
+            memory_cost=settings.ARGON2_MEMORY_COST,
+        ),
+        BcryptHasher(),
+    )
+)
```

未更换算法（仍是 Argon2id），未绕过校验。参数实测对照（本机、单次）：

| time_cost | memory_cost | hash P50 |
|---|---|---|
| 3 | 64 MiB（原默认） | 111.0 ms |
| **2** | **32 MiB（采用）** | **32.6 ms** |
| 2 | 19 MiB | 20.9 ms |

选 32 MiB / t=2 而非更激进的档位，是为了仍在 OWASP 建议下限（19 MiB / t=2）之上。

---

## 3. 次要 4：runner 的 JMeter 环境判断

### 3.1 diff — `backend/tests/platform/runner.py`

```diff
 def run_jmeter(jmeter_dir: Path, results_dir: Path) -> dict[str, Any]:
-    jmeter_bin = shutil.which(CONFIG.env.jmeter_bin)
-    if not jmeter_bin:
-        return {"status": "na", "scenarios": [],
-                "note": "未检测到 JMeter/Java，跳过性能测试（.jmx 已就绪，可在具备 Java 环境运行）"}
+    jmeter_bin, note = resolve_jmeter()
+    if not jmeter_bin:
+        return {"status": "na", "scenarios": [], "note": note}

+def resolve_jmeter() -> tuple[str | None, str]:
+    """解析 JMeter 可执行文件路径，返回 (路径, 未找到时的说明)。
+
+    Windows 下 JMeter 只提供 jmeter.bat，直接 shutil.which("jmeter") 必然找不到，
+    因此按平台展开候选（含 JMETER_HOME/bin、.bat 后缀）；JMeter 依赖 JVM，
+    Java 缺失时同样按「环境不具备」处理，跳过套件而不是报错。
+    """
+    configured = CONFIG.env.jmeter_bin
+    candidates: list[str] = [configured]
+    if os.name == "nt" and not configured.lower().endswith((".bat", ".cmd", ".exe")):
+        candidates.append(configured + ".bat")
+    jmeter_home = os.environ.get("JMETER_HOME", "")
+    if jmeter_home:
+        bin_dir = Path(jmeter_home) / "bin"
+        candidates += [str(bin_dir / "jmeter.bat"), str(bin_dir / "jmeter")]
+
+    for cand in candidates:
+        if not cand:
+            continue
+        found = shutil.which(cand)
+        if found:
+            return found, ""
+        if Path(cand).is_file():          # 直接给出绝对/相对路径时也接受
+            return str(Path(cand)), ""
+
+    if shutil.which("java") is None:
+        return None, "未检测到 Java（JMeter 依赖 JVM），跳过性能测试"
+    tried = " / ".join(c for c in candidates if c)
+    return None, (
+        f"未检测到 JMeter（已尝试：{tried}），跳过性能测试；"
+        f"可设置 JMETER_HOME 指向 JMeter 安装目录（Windows 下实际可执行文件为 jmeter.bat）"
+    )
```

原逻辑用 `shutil.which("jmeter")`，Windows 上 JMeter 只提供 `jmeter.bat`，必然找不到而静默标 `na`。现在实测本机能解析到 `C:\apache-jmeter-5.6.3\bin\jmeter.BAT`。

**注意**：本机 `JMETER_HOME` 已设置，runner 现在会真的去跑那 8 个 `.jmx`——而它们与 JMeter 5.6.3 的 xstream 解析不兼容（次要 1），所以性能套件会从「跳过」变成「真实失败」。这是更诚实的信号，但如只想跑功能套件可加 `--no-jmeter`。

---

## 4. 验证命令与运行结果

### 4.1 P01：空白库完整执行 `alembic upgrade head`

```bash
docker exec qa-pg psql -U postgres -c "DROP DATABASE IF EXISTS qa_blank;" -c "CREATE DATABASE qa_blank;"

cd backend
export POSTGRES_SERVER=localhost POSTGRES_PORT=15432 POSTGRES_USER=postgres \
       POSTGRES_PASSWORD=postgres123 POSTGRES_DB=qa_blank SECRET_KEY=qa-test-secret-key
.venv/Scripts/python.exe -m alembic heads          # 校验单头无分叉
.venv/Scripts/python.exe -m alembic upgrade head
```

结果（无异常，24 个 revision 全部跑完）：

```
INFO  ... Running upgrade f1a2b3c4d5e6 -> i5j6k7l8m9n0, add missing core tables
INFO  ... Running upgrade i5j6k7l8m9n0 -> f2b3c4d5e6a7, add homework, submission ...
INFO  ... Running upgrade f2b3c4d5e6a7 -> g3h4i5j6k7l8, add submissiongrade table ...
INFO  ... Running upgrade g3h4i5j6k7l8 -> h4i5j6k7l8m9, add submission.superseded ...
```

`alembic heads` → `h4i5j6k7l8m9 (head)`，单头无分叉。

### 4.2 P01：schema 与 ORM metadata 一致性校验

```bash
cd backend
.venv/Scripts/python.exe tests/perf/verify_schema.py
```

结果：

```
DB 表数: 28  metadata 表数: 27
metadata 有但 DB 缺: 无

【一致】所有共有表的列与外键均与 metadata 匹配
```

外键总数 **45 条**（加 `use_alter=True` 时 homework / organization 上为 0 条）：

```
homework.homework_lesson_plan_id_fkey / homework_org_id_fkey / homework_owner_id_fkey
organization.organization_parent_id_fkey
user.user_org_id_fkey
lessonplan.lessonplan_template_id_fkey
...
```

### 4.3 P01：回滚 / 重做可逆性

```bash
.venv/Scripts/python.exe -m alembic downgrade f1a2b3c4d5e6
.venv/Scripts/python.exe -m alembic upgrade head      # 重做
.venv/Scripts/python.exe tests/perf/verify_schema.py
```

结果：downgrade 与重做均无异常，重做后 schema 仍与 metadata 一致。
（若不在 downgrade 里 `DROP TYPE`，重做会报 `type "homeworkstatus" already exists`，这是顺带修掉的。）

### 4.4 P01：迁移建出的库能否真正跑应用

```bash
POSTGRES_DB=qa_blank NEO4J_URI=bolt://localhost:17687 ... \
  .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18002

curl 注册 + 登录
```

结果：

```
signup: 200
login:  200  token_len=165
```

即不只是「迁移不报错」，迁移产出的库能正常完成注册/登录。

### 4.5 P02：单次哈希耗时与向后兼容

```bash
cd backend
.venv/Scripts/python.exe tests/perf/verify_hash.py
```

结果：

```
ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST = 32768 KiB

hash  P50 = 32.6 ms   P95 = 35.8 ms   max = 37.0 ms
verify P50 = 42.7 ms  P95 = 74.5 ms   max = 96.5 ms
verify 结果 = True
旧参数哈希校验 = True (True 表示老用户密码不受影响)

结论：单次哈希 P95 35.8 ms < 300ms 阈值，达标；新旧哈希均可校验。
```

### 4.6 P02：登录接口端到端（与修复前同口径）

```bash
.venv/Scripts/python.exe tests/perf/perf_smoke.py --host 127.0.0.1 --port 18002 \
    --total 100 --concurrency 10
```

并发 10：

| 场景 | 修复前 P50 | 修复前 P95 | 修复后 P50 | 修复后 P95 | 判定 |
|---|---|---|---|---|---|
| 登录获取令牌 | 619 ms | 745 ms | **276.8 ms** | **343.6 ms** | PASS（≤500ms）|
| 读取当前用户 | — | — | 41.4 ms | 83.4 ms | PASS |
| 教案列表 | — | — | 37.8 ms | 74.3 ms | PASS |
| 作业列表 | — | — | 43.1 ms | 77.7 ms | PASS |
| 知识点列表 | — | — | 111.9 ms | 289.3 ms | FAIL（次要 2）|
| 学科列表 | — | — | 40.1 ms | 72.3 ms | PASS |
| 提醒-课程表 | — | — | 47.8 ms | 107.2 ms | PASS |

并发 50（对照）：登录 P95 **4401 ms → 1851 ms**，知识点列表 P95 1107 ms → 754 ms，错误率始终 0%。

### 4.7 回归门禁

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests -q
```

结果：**236 passed, 2 warnings in 13.49s**（与修复前一致，0 失败）。

### 4.8 ruff（仅处理本次改动引入的告警）

```bash
.venv/Scripts/ruff.exe check --output-format=concise \
  app/alembic/versions/i5j6k7l8m9n0_add_missing_core_tables.py \
  app/alembic/versions/c9e2f4a1b0d3_add_candidate_kind.py \
  app/core/config.py app/core/security.py
```

结果：`All checks passed!`

本次改动引入的 8 项告警（6×UP032、2×I001）已全部清除。既有告警按约定保留未动：
`f2b3/g3/h4` 的 I001、`g3` 的 F401、`runner.py` 的 UP009 与 9 处 T201。

---

## 5. 次要遗留（本次只标记，未改代码）

| # | 事项 | 现状 | 建议 |
|---|------|------|------|
| 1 | `.jmx` 与 JMeter 5.6.3 解析不兼容 | xstream 反序列化失败（HeaderManager / HTTPSamplerProxy） | 用 JMeter 5.6.3 重新导出一份 jmx，或继续用 `tests/perf/perf_smoke.py` |
| 2 | 并发 50 读接口容量不足 | 并发 50 时 7/7 场景 P95 超阈值（错误率 0%） | 加缓存 / 连接池调优 / 知识点列表走 Neo4j 的查询优化 |
| 3 | ruff 230 条告警 | 本次改动产生的已清零，历史存量未动 | 分批清理，优先 T201 与 F401 |
| 4 | Windows runner 找不到 jmeter | 已修：按平台展开 `jmeter.bat` / `JMETER_HOME` 候选，缺 Java 也明确跳过 | — |
