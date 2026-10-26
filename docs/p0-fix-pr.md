# P0 修复：环境处置方案 / 合并门禁清单 / PR 描述

日期：2026-10-26 · 本文只做方案与文案输出，**未执行任何停止/删除容器或进程的操作**

---

## 一、环境处置方案对比

### 当前占用（实测）

| 对象 | 内存 | 磁盘（镜像 virtual） |
|---|---|---|
| `qa-neo4j`（neo4j:5，17474/17687） | 748.6 MiB | 897 MB |
| `qa-pg`（postgres:15-alpine，15432） | 65.1 MiB | 301 MB |
| 后端 uvicorn `18002`（PID 3372） | ~19.5 MB | — |
| **合计** | **≈ 833 MB 常驻** | **≈ 1.2 GB** |

（另有与本项目无关的 dify 容器栈在跑，不在处置范围。）

### 方案 A：保留 QA 环境，用于后续迭代验证

| 维度 | 内容 |
|---|---|
| 动作 | 停 uvicorn 进程 + `docker stop qa-pg qa-neo4j`（**不删除**） |
| 释放 | 内存即时归还 ≈833 MB；磁盘继续占用 ≈1.2 GB |
| 数据 | 全保留：`qa_blank` 验证库、`app` 旧库、Neo4j 演示图谱 |
| 恢复 | `docker start qa-pg qa-neo4j`，镜像本机已有，秒级恢复 |
| 适用 | 还要做并发容量调优 / jmx 重导 / ruff 分批清理后的回归 |
| 风险 | 无（容器停止不丢数据） |

### 方案 B：全部停止并销毁，释放资源

| 维度 | 内容 |
|---|---|
| 动作 | 停 uvicorn + `docker rm -f qa-pg qa-neo4j` |
| 释放 | ≈833 MB 内存 + ≈1.2 GB 磁盘（镜像层未被共享时才真正回收） |
| 数据 | **全部丢失**：Neo4j 演示图谱、`qa_blank`、`app` 库 |
| 恢复 | 需重新起容器（镜像不用重拉）+ 重灌演示库 + 重跑验证，约 10–15 分钟 |
| 适用 | 本轮即终点，短期不再动此项目 |
| 风险 | 销毁不可逆；如需留档必须先备份 |

### 决策建议

倾向 **方案 A**。本轮留下 3 项次要遗留（jmx 不兼容、并发 50 容量、ruff 存量），其中「并发容量调优」几乎必然要再压测一次；重建环境的成本高于 1.2 GB 磁盘占用。只有在确认本轮彻底收尾时才值得走方案 B。

> 销毁前如需备份（**仅在你确认后执行**）：
> ```bash
> docker exec qa-pg pg_dumpall -U postgres > qa-pg-backup.sql
> docker exec qa-neo4j neo4j-admin database dump neo4j --to-path=/var/lib/neo4j/dumps
> docker cp qa-neo4j:/var/lib/neo4j/dumps ./qa-neo4j-backup
> ```

---

## 二、合并前门禁检查清单（可直接复制执行）

> 环境：Windows + Git Bash，仓库根 `E:\work\tty-main\tty-main`。
> 若没有 Docker QA 容器，把 `POSTGRES_*` 换成任意空白 Postgres 库即可，其余命令不变。

### 步骤 0 —— 进入后端目录

```bash
cd E:/work/tty-main/tty-main/backend
```

### 步骤 1 —— 提交完整性（最容易翻车的一步）

本次 5 个迁移文件在 git 中是 **untracked**，用 `git add -u` 会全部漏掉，生产部署直接失败：

```bash
git add -A app/alembic/versions tests/perf tests/platform/runner.py \
        app/core/config.py app/core/security.py
git status --short
```

**必须确认** `i5j6k7l8m9n0_add_missing_core_tables.py` 出现在待提交列表里。

### 步骤 2 —— 单元测试门禁

```bash
./.venv/Scripts/python.exe -m pytest tests -q
```

期望：`236 passed`

> 排障：若 `tests/ai_eval/test_ai_eval.py` 报 `PermissionError: ... ai_eval.json`，
> 是结果文件被占用（本机已复现：删掉后首次运行必过，之后每次再跑都会锁）。
> 清掉产物重跑即可，**不是代码问题**：
> ```bash
> rm -f tests/ai_eval/results/ai_eval.json
> ./.venv/Scripts/python.exe -m pytest tests -q
> ```

### 步骤 3 —— 迁移链单头无分叉

```bash
export POSTGRES_SERVER=localhost POSTGRES_PORT=15432 POSTGRES_USER=postgres \
       POSTGRES_PASSWORD=postgres123 POSTGRES_DB=qa_gate SECRET_KEY=qa-test-secret-key

./.venv/Scripts/python.exe -m alembic heads
```

期望：输出**只有一行** `h4i5j6k7l8m9 (head)`。多行 = 分叉，必须先解决。

> PowerShell 写法：
> ```powershell
> $env:POSTGRES_SERVER="localhost"; $env:POSTGRES_PORT="15432"
> $env:POSTGRES_USER="postgres";   $env:POSTGRES_PASSWORD="postgres123"
> $env:POSTGRES_DB="qa_gate";      $env:SECRET_KEY="qa-test-secret-key"
> ```

### 步骤 4 —— 空白库完整 upgrade（P01 验收标准）

```bash
docker exec qa-pg psql -U postgres -c "DROP DATABASE IF EXISTS qa_gate;" -c "CREATE DATABASE qa_gate;"
./.venv/Scripts/python.exe -m alembic upgrade head
```

期望：24 个 revision 依次 `Running upgrade ...`，无异常退出。

### 步骤 5 —— schema 与 ORM metadata 一致性

```bash
./.venv/Scripts/python.exe tests/perf/verify_schema.py; echo "退出码=$?"
```

期望：

```
目标库: localhost:15432/qa_gate
DB 表数: 28  metadata 表数: 27
metadata 有但 DB 缺: 无
外键总数: 45
【一致】所有共有表的列 / 外键 / 索引均与 metadata 匹配
退出码=0
```

（脚本已支持 `POSTGRES_*` 环境变量；不一致时以退出码 1 失败，可直接挂 CI。）

### 步骤 6 —— downgrade / upgrade 闭环可逆

```bash
./.venv/Scripts/python.exe -m alembic downgrade f1a2b3c4d5e6
./.venv/Scripts/python.exe -m alembic upgrade head
./.venv/Scripts/python.exe tests/perf/verify_schema.py; echo "退出码=$?"
```

期望：两步均无异常，重做后仍是「一致」、退出码 0。

### 步骤 7 —— 哈希耗时与向后兼容（P02 验收标准）

```bash
./.venv/Scripts/python.exe tests/perf/verify_hash.py; echo "退出码=$?"
```

期望：

```
ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST = 32768 KiB
hash  P50 ≈ 28~33 ms   P95 < 300 ms
旧参数哈希校验 = True
退出码=0
```

### 步骤 8 —— 改动文件静态检查

ruff 可执行文件在仓库根的 `.venv`，不在 `backend/.venv`：

```bash
../.venv/Scripts/ruff.exe check --output-format=concise \
  app/alembic/versions/i5j6k7l8m9n0_add_missing_core_tables.py \
  app/alembic/versions/c9e2f4a1b0d3_add_candidate_kind.py \
  app/core/config.py app/core/security.py \
  tests/perf/verify_schema.py tests/perf/verify_hash.py
```

期望：`All checks passed!`

> 说明：迁移目录在 `pyproject.toml` 的 `exclude = ["alembic"]` 里，CI 全量扫描不会计入；
> 上面是显式指定路径检查。本次新增告警必须为 **0**。

### 步骤 9 —— 前端（本次未改动，可跳过）

本轮改动全部在后端。若分支上还含前几轮的前端改动，补跑：

```bash
cd ../frontend && npx vue-tsc --noEmit
```

### 步骤 10 —— 跑测试平台时注意

`runner.py` 修复后，本机（`JMETER_HOME` 已设置）会真的去执行 8 个与 JMeter 5.6.3 不兼容的 `.jmx`，
性能套件会从「跳过」变成「失败」。只跑功能套件请加 `--no-jmeter`：

```bash
cd tests/platform && python runner.py --scope api --no-jmeter
```

### 步骤 11 —— 目标环境部署前核查

对每个待部署环境执行：

```sql
SELECT version_num FROM alembic_version;
```

本轮在链中间插入了 revision，若某环境的 `alembic_version` 落后于真实 schema（早期用 `create_all` 建表后手工 stamp），
先在预发完整演练一次 `upgrade head`，不要直接在生产跑。可用 `tests/perf/verify_schema.py` 逐环境比对。

---

## 三、PR 描述（可直接粘贴）

```markdown
## 背景

两个 P0 阻塞问题导致生产部署链路失效 / 登录性能不达标，本次只做最小修复，
未改动业务逻辑、数据模型与已有测试用例（236 个用例保持全绿）。

## P01 全新空库 `alembic upgrade head` 失败

**现象**：执行到 `f2b3c4d5e6a7` 建 `homework` 表时报
`UndefinedTable: relation "organization" does not exist`（SQLAlchemy f405），
只能靠 `SQLModel.metadata.create_all()` 绕过，生产部署流程失效。

**真实根因**（与原判断不同，不是单纯的建表顺序问题）：
`organization` 等 **10 张核心表从未被任何 revision 创建**。用 metadata 与迁移链
做全量比对后确认缺口为：
`organization` / `permission` / `role` / `userrole` / `rolepermission` /
`resourceacl` / `reviewrecord` / `contributionevent` /
`lessonplantemplate` / `lessonplanversionsnapshot`

**关于 `use_alter=True` 的重要结论**：
最初按「外键后置」思路给 `ForeignKeyConstraint` 加了 `use_alter=True`，迁移能跑通，
但校验发现**外键一条都没建出来**——该标记只对 `metadata.create_all()` 的拓扑排序生效，
`op.create_table()` 会静默忽略它，既不进 `CREATE TABLE` 也不补发 `ALTER`。
这类静默失败比直接报错更危险，已改为 alembic 原生支持的方式：
**先 `CREATE TABLE`（不带外键），再统一 `op.create_foreign_key()` 追加**，
等价于 `ALTER TABLE ADD CONSTRAINT`，效果与「先建表后追加外键」一致。

**同时修复的 4 类连带问题**（不改的话库能建出来但运行时必挂）：
1. 表名不一致：迁移写 `submission_grade` / `mistake_feedback`，ORM 期望 `submissiongrade` / `mistakefeedback`
2. 枚举持久化口径：SQLAlchemy 存的是成员名 `DRAFT`，迁移写的是值 `draft` → `invalid input value for enum`
3. `user` / `lessonplan` 上 8 个从未被迁移过的字段（org_id / group_id / status / visibility / source_type / version / template_id）
4. 漏建索引 `ix_candidateknowledgepoint_kind`
另修：downgrade 时枚举类型残留导致再次 upgrade 报 `type already exists`。

**验证**：
- 空白库 `alembic upgrade head` 全量跑完，24 个 revision 无异常
- `alembic heads` 单头 `h4i5j6k7l8m9`，无分叉
- `verify_schema.py`：27 张表全在，45 条外键齐全，列/外键/索引与 metadata 完全一致
- downgrade → upgrade 闭环可逆
- 迁移产出的库能正常完成注册 + 登录（200 / 200）

## P02 登录接口 P50 619ms

**根因**：argon2 哈希成本过高，与 DB 无关。

**改动**：`time_cost 3 → 2`、`memory_cost 65536 → 32768 KiB`（32 MiB），
算法仍为 Argon2id，未绕过任何密码校验，parallelism 未动。
参数由 `settings.ARGON2_TIME_COST` / `ARGON2_MEMORY_COST` 下发，便于按环境调整。
选 32 MiB / t=2 而非更激进档位，是为了仍在 OWASP 建议下限（19 MiB / t=2）之上。

**效果**：
| 指标 | 修复前 | 修复后 |
|---|---|---|
| 单次哈希 P50 | 111 ms | 32.6 ms |
| 登录 P50 / P95（并发 10） | 619 / 745 ms | 276.8 / 343.6 ms |
| 登录 P95（并发 50） | 4401 ms | 1851 ms |

**兼容性**：argon2 参数写入哈希串，旧参数生成的哈希仍能正常 verify，
**无需重置用户密码**（已用旧参数哈希实测通过）。

## runner JMeter 路径适配（Windows）

`shutil.which("jmeter")` 在 Windows 上必然失败（JMeter 只提供 `jmeter.bat`），
性能套件被静默标记为 `na`。改为按平台展开候选：`jmeter.bat` 后缀 + `JMETER_HOME/bin`，
并对 Java 缺失单独给出明确提示。

**注意**：本机 `JMETER_HOME` 已设置，修复后 runner 会真的执行那 8 个与 JMeter 5.6.3
不兼容的 `.jmx`，性能套件由「跳过」变为「失败」。只跑功能套件需加 `--no-jmeter`。

## 影响范围

仅迁移脚本 / 哈希配置 / runner 环境判断，未改动业务逻辑、数据模型与已有测试用例。
新增 `backend/tests/perf/verify_schema.py`、`verify_hash.py` 两个校验脚本
（非 `test_` 前缀，不被 pytest 收集，可直接挂 CI）。

## 验证结果

- `pytest tests -q` → **236 passed**（与修复前一致，0 失败）
- 空白库 `alembic upgrade head` → 无异常
- `verify_schema.py` → 一致，退出码 0
- `verify_hash.py` → P95 < 300ms，旧哈希可校验，退出码 0
- 改动文件 ruff → `All checks passed!`（本次新增告警 0）

## 后续（本次未处理，仅记录）

1. 8 个 `.jmx` 与 JMeter 5.6.3 的 xstream 解析不兼容，需用 5.6.3 重新导出
2. 并发 50 时读接口 P95 仍超阈值（错误率 0%，属容量问题，非稳定性问题）
3. ruff 存量告警（`backend/` 全局 295 项）分批清理，优先 T201 / ARG001 / I001
4. **建议单独排期**：`app/core/db.py` 启动时的 `create_all()` 兜底会掩盖迁移漂移，
   这正是本次 10 张表缺失长期未被发现的原因。建议加环境开关限制在非生产，
   或把 `verify_schema.py` 挂进 CI 做漂移检测
```

---

## 四、待确认（未执行）

1. 环境处置走方案 A 还是方案 B？销毁前是否需要备份 Neo4j 演示图谱与 `qa_blank`？
2. 是否要把 `verify_schema.py` 挂进 CI（对应上面第 4 条）？
3. 3 项次要遗留（jmx / 并发容量 / ruff 存量）是否在下一轮处理？

**在你确认前，不会执行任何停止或删除操作。**
