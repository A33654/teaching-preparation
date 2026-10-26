# P0 修复收尾：环境处置建议 / 遗留风险 / 合并前检查清单

日期：2026-10-26 · 修复动作已落地并完成多轮验证 · 本文只做盘点与建议，**未执行任何删除动作**

---

## 一、环境清理：两方案对比

### 当前环境实测占用

| 对象 | 内存 | CPU | 镜像体积（virtual） |
|---|---|---|---|
| `qa-neo4j`（neo4j:5） | 748.6 MiB | 1.53% | 897 MB |
| `qa-pg`（postgres:15-alpine） | 65.1 MiB | 0.79% | 301 MB |
| 后端 uvicorn `18002`（PID 3372） | ~19.5 MB | 近空闲 | — |
| **合计** | **≈ 833 MB 常驻** | | **≈ 1.2 GB 磁盘** |

另：机器上有与本项目无关的 dify 容器栈在跑（不在本次处置范围）。

### 方案 A：保留 QA 环境（推荐，若短期内还有迭代）

| 维度 | 说明 |
|---|---|
| 做法 | 停掉 uvicorn 进程，保留两个容器（`docker stop`，不删除） |
| 释放 | 立即释放 ≈20 MB；容器停止后内存也会归还（再省 ≈813 MB） |
| 数据 | 全部保留：`qa_blank` 迁移验证库、`app` 旧库、Neo4j 演示图谱 |
| 恢复成本 | 极低——`docker start qa-pg qa-neo4j` 即可，镜像无需重拉 |
| 后续适用 | 继续做并发容量调优（次要 2）、重导 jmx（次要 1）、ruff 清理后回归 |
| 代价 | 磁盘继续占用 ≈1.2 GB |

命令（**待你确认后我再执行**）：

```bash
# 停后端进程
netstat -ano | grep ":18002"          # 取监听 PID
# PowerShell: Stop-Process -Id <PID> -Force

# 停容器（保留数据卷与镜像）
docker stop qa-pg qa-neo4j

# 恢复
docker start qa-pg qa-neo4j
```

### 方案 B：全部销毁释放资源

| 维度 | 说明 |
|---|---|
| 做法 | 停 uvicorn + `docker rm -f qa-pg qa-neo4j` |
| 释放 | ≈833 MB 内存 + ≈1.2 GB 磁盘（镜像层如未被其他容器共享才会真正回收） |
| 数据 | **全部丢失**——含 Neo4j 演示图谱、`qa_blank` 验证库 |
| 恢复成本 | 中：需重新起容器（镜像本机已有，无需重拉）+ 重新灌演示库 + 重跑一遍验证 |
| 后续适用 | 本轮工作已彻底收尾、短期内不再动这个项目 |
| 代价 | 下次迭代要重搭环境，约 10–15 分钟 |

如需销毁但想留数据，先备份（**待确认后执行**）：

```bash
docker exec qa-pg pg_dumpall -U postgres > qa-pg-backup.sql
docker exec qa-neo4j neo4j-admin database dump neo4j --to-path=/var/lib/neo4j/dumps
docker cp qa-neo4j:/var/lib/neo4j/dumps ./qa-neo4j-backup
```

### 决策建议

倾向 **方案 A**，理由：本轮留下了 3 项次要遗留（jmx 不兼容、并发容量、ruff 295 项），其中并发容量调优几乎必然要再压测，重建环境的成本高于 1.2 GB 磁盘。若你确认本轮就是终点，再走方案 B。

---

## 二、遗留风险清单

> 严重度：高 = 会影响部署或数据；中 = 影响质量/效率；低 = 体验或技术债

### R-1 · 8 条 jmx 与 JMeter 5.6.3 解析不兼容 —— 中

文件：`backend/tests/jmeter/`
`01-auth-login` `02-kp-list-graph` `03-lesson-plan-crud` `04-doc-upload`
`05-chat-sse` `06-admin-batch` `07-mixed-load` `08-stress-ramp`

- xstream 反序列化失败（HeaderManager / HTTPSamplerProxy），JMeter 5.6.3 无法加载。
- **本次的连带影响**：runner 修好路径识别后，本机（`JMETER_HOME` 已设置）会从「静默跳过」变成「真实执行并失败」。跑功能套件需显式加 `--no-jmeter`。
- 建议：用 5.6.3 重新导出一份 jmx；在修好前性能口径以 `tests/perf/perf_smoke.py` 为准。

### R-2 · 并发 50 读接口容量不足 —— 中（本次未碰）

- 并发 50 时 7/7 场景 P95 超阈值（错误率恒为 0%，是容量问题不是稳定性问题）。
- 知识点列表最差：P95 754 ms（修复前 1107 ms，本次因登录不再抢占资源而顺带改善）。
- 登录 P95 并发 50 仍为 1851 ms > 500 ms 阈值——P02 解决的是「单请求成本」，不是「并发吞吐」。
- 建议：知识点列表走 Neo4j，优先查图查询与缓存；登录可在网关层做限流。

### R-3 · ruff 告警 —— 低（数量需更正）

**更正一处数字**：你汇总里的「230 项」与实际不符，当前实测是：

| 范围 | 告警数 |
|---|---|
| `backend/` 全局 | **295** |
| `app/alembic/versions/` 全部迁移 | 32 |
| **本次改动/新增的 8 个文件** | **14** |

- 这 14 项**全部是既有告警**（f2b3/g3/h4 的 I001 共 4 项、runner.py 的 UP009 + 9 处 T201），**本次新增为 0**——原本引入的 8 项（6×UP032 + 2×I001）已清零。
- 建议：按规则分批清，优先级 T201(78) → ARG001(70) → I001(40) → UP009(24) → F401(24)。

### R-4 · 存量库的 `alembic_version` 与真实 schema 可能不一致 —— **高（新增，需重点关注）**

本轮在迁移链中间插入了新 revision `i5j6k7l8m9n0`（位于 `f1a2b3c4d5e6` 与 `f2b3c4d5e6a7` 之间）。逻辑上：

- 已在 head 的库：不会重跑新 revision（本来就有这些表），安全。
- **风险场景**：某个环境此前用 `create_all` 建表后再手工 `alembic stamp` 到某个早期版本，或只跑过部分迁移——它的 `alembic_version` 落后于真实 schema，升级时会跑 `i5j6k7l8m9n0`。虽然每个动作都有 `_table_exists` / `_column_exists` / `_fk_exists` 幂等保护，但**升级前必须先核对**。

部署前必查（每个环境）：

```sql
SELECT version_num FROM alembic_version;
SELECT count(*) FROM information_schema.tables WHERE table_schema='public';
```

建议用 `backend/tests/perf/verify_schema.py` 对每个环境跑一遍，它直接比对 DB 与 `SQLModel.metadata`。

### R-5 · `create_all` 兜底会掩盖迁移漂移 —— **高（根因层面，新增）**

`backend/app/core/db.py:25` 在启动时执行 `SQLModel.metadata.create_all(engine)`，注释写的是「与 Alembic 互补 / 兜底」。

**这正是迁移缺口能长期存活不被发现的原因**：新模型不写迁移也能跑起来，直到有人在新环境执行 `alembic upgrade head` 才炸。

建议（二选一，均不在本次改动范围，需你决策）：

1. 用开关把 `create_all` 限制在非生产环境（例如 `settings.CREATE_ALL_ON_STARTUP`，生产置 False），强制结构变更必须走迁移；
2. 保留 `create_all`，但把 `verify_schema.py` 挂到 CI——每次提交用空白库跑 `alembic upgrade head` 后比对 metadata，漂移即失败。

### R-6 · 新增迁移文件是 untracked，提交时容易漏 —— **高（流程）**

`git status` 显示 5 个迁移文件为 `??`（未跟踪）：

```
?? f1a2b3c4d5e6_add_review_note_to_knowledge_suggestion.py
?? f2b3c4d5e6a7_add_homework_submission_and_lp_exercises.py
?? g3h4i5j6k7l8_add_submission_grade_and_graded_at.py
?? h4i5j6k7l8m9n0_add_superseded_ai_unavailable_mistake_feedback.py
?? i5j6k7l8m9n0_add_missing_core_tables.py   ← 本次 P01 的核心修复
```

若用 `git add -u` 或只提交已跟踪文件，这些迁移会全部丢失，生产部署直接失败。**必须显式 `git add`**。

### R-7 · `lessonplan` 存量行会被赋予默认状态 —— 低

补加 `lessonplan.status` 时用了 `server_default='DRAFT'`（NOT NULL 列必须有默认值才能加在有数据的表上），随后 `alter_column` 去掉了默认值。

影响：已有教案行的 status 会被填成 `DRAFT`。若存量库里存在已发布/已审核的教案，需要确认这批数据是否需要按业务回填真实状态。默认值与模型定义一致（`LessonPlanStatus.DRAFT`），不会引发不一致。

### R-8 · 生产部署链路上还有一步手工迁移脚本 —— 低

`backend/scripts/migrate_kgs_to_neo4j.py` 的注释与输出提示「在 alembic upgrade 前运行一次」，而 `prestart.sh` 只跑 `alembic upgrade head`，不含这一步。全新环境部署时若漏跑，知识点/关系不会进 Neo4j。建议确认该脚本是否仍需手工执行。

---

## 三、合并前检查清单（必跑）

> 假设工作目录 `E:\work\tty-main\tty-main`，后端虚拟环境 `backend/.venv`

### 1. 提交完整性（最容易翻车的一步）

```bash
git add -A backend/app/alembic/versions/ backend/tests/perf/ \
         backend/app/core/config.py backend/app/core/security.py \
         backend/tests/platform/runner.py docs/p0-fix-diff.md docs/p0-fix-closeout.md
git status --short
```

期望：上面 5 个迁移文件从 `??` 变为 `A`/`M`，`i5j6k7l8m9n0_...py` 必须在列。

### 2. 单元测试门禁

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests -q
```

期望：`236 passed`（与修复前一致，0 失败）。

### 3. 迁移链完整性

```bash
cd backend
export POSTGRES_SERVER=localhost POSTGRES_PORT=15432 POSTGRES_USER=postgres \
       POSTGRES_PASSWORD=postgres123 POSTGRES_DB=qa_blank SECRET_KEY=qa-test-secret-key
.venv/Scripts/python.exe -m alembic heads
```

期望：输出**单行** `h4i5j6k7l8m9 (head)`。出现多行 = 存在分叉，必须处理。

### 4. 空白库完整迁移（P01 验收标准）

```bash
docker exec qa-pg psql -U postgres -c "DROP DATABASE IF EXISTS qa_merge_check;" -c "CREATE DATABASE qa_merge_check;"
cd backend
POSTGRES_DB=qa_merge_check ... .venv/Scripts/python.exe -m alembic upgrade head
```

期望：24 个 revision 全部 `Running upgrade ...`，无任何异常退出。

### 5. schema 与 ORM 一致性

```bash
cd backend
.venv/Scripts/python.exe tests/perf/verify_schema.py   # 注意改 DATABASE 指向 qa_merge_check
```

期望：

```
DB 表数: 28  metadata 表数: 27
metadata 有但 DB 缺: 无
【一致】所有共有表的列与外键均与 metadata 匹配
```

### 6. 回滚可逆性

```bash
.venv/Scripts/python.exe -m alembic downgrade f1a2b3c4d5e6
.venv/Scripts/python.exe -m alembic upgrade head
```

期望：两步均无异常；重做后再跑一次 `verify_schema.py` 仍为「一致」。

### 7. 哈希参数与向后兼容（P02 验收标准）

```bash
cd backend
.venv/Scripts/python.exe tests/perf/verify_hash.py
```

期望：

```
hash  P50 ≈ 32.6 ms   P95 < 300 ms
旧参数哈希校验 = True
```

### 8. 本次改动文件的静态检查

```bash
.venv/Scripts/ruff.exe check --output-format=concise \
  app/alembic/versions/i5j6k7l8m9n0_add_missing_core_tables.py \
  app/alembic/versions/c9e2f4a1b0d3_add_candidate_kind.py \
  app/core/config.py app/core/security.py
```

期望：`All checks passed!`（本次新增告警必须为 0）

补充：改动 8 个文件的全量检查为 14 项，**全部为历史存量**，不应比这个数字更多。

### 9. 前端（本次未改动，可跳过）

本次改动全部在后端，前端 `frontend/` 未触碰。若合并分支上还含前几轮的前端改动，则补跑：

```bash
cd frontend && npx vue-tsc --noEmit
```

### 10. 目标环境部署前核查（针对 R-4 / R-5）

对每个待部署环境执行：

```sql
SELECT version_num FROM alembic_version;
```

并用 `verify_schema.py` 比对一次。若 `alembic_version` 落后于真实 schema，先在预发环境完整演练一次 `upgrade head`，不要直接在生产跑。

---

## 四、待你确认的事项

1. **环境清理决策**：方案 A（保留，停进程 + 停容器）还是方案 B（销毁并释放资源）？销毁前是否需要先备份 Neo4j 演示图谱与 `qa_blank` 库？
2. **R-5 的处置方向**：是否要把 `create_all` 加环境开关限制在非生产，或把 `verify_schema.py` 挂进 CI？这决定了后续会不会再次出现同类迁移漂移。
3. **次要遗留的排期**：jmx 重导（R-1）、并发容量调优（R-2）、ruff 分批清理（R-3）——是否需要在下一轮处理，还是仅记录在案。

在你确认前，**不会执行任何删除/停止动作**。
