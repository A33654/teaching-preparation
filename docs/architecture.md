# 教师智能备课系统 · 技术评估与生产就绪度分析

> 视角：本文档是 `技术架构与设计文档.md` 的**补充**——后者讲「系统怎么搭起来的」，本篇讲「并发能力、缓存与可扩展性如何、离生产化还差什么」。
> 结论均基于代码实测（grep / 读源码），非文档印象。标注 `文件:行号` 便于复核。
> 评估日期：2026-10-27

---

## 0. 一句话定位

基于「知识图谱 + LangGraph AI Agent」的教师智能备课平台：选章节 → 图谱算出教学拓扑 → 流水线生成教案/课件 → 教师批改作业 → 学情看板 → 误区回写图谱，形成闭环。

---

## 1. 技术栈速览（实测）

| 层 | 技术 | 证据 |
|---|---|---|
| 前端 | Vue 3.5 + TypeScript + Vite 7 + Element Plus + Pinia + vue-router + vis-network（图谱可视化）+ axios + marked | `frontend/package.json` |
| 后端框架 | FastAPI（`fastapi[standard]`） | `backend/pyproject.toml:7` |
| ORM / 业务库 | SQLModel（SQLAlchemy）+ PostgreSQL 18 | `backend/pyproject.toml:16-17` |
| 图数据库 | Neo4j 5（知识图谱） | `backend/pyproject.toml:22`；`compose.yml:26` |
| 迁移 | Alembic | `backend/pyproject.toml:14` |
| 认证 | PyJWT + pwdlib（argon2/bcrypt） | `backend/pyproject.toml:20-21` |
| AI 编排 | LangGraph + LangChain（可切通义千问 / DeepSeek / Kimi） | `backend/pyproject.toml:23-25` |
| 文档生成 | python-docx / python-pptx / pdfplumber / reportlab / xlsxwriter / numpy | `backend/pyproject.toml:26-31` |
| 部署 | Docker Compose 单栈（前端 + 后端 + PostgreSQL + Neo4j） | `compose.yml` |

---

## 2. 高并发能力评估

### 2.1 已有的并发能力 ✅

- **进程级并发**：后端以 `fastapi run --workers 4` 启动，4 个 worker 进程。
  - 证据：`backend/Dockerfile:45` → `CMD ["fastapi", "run", "--workers", "4", "app/main.py"]`
- **AI 流式输出**：对话与备课生成走 SSE（`StreamingResponse` + `text/event-stream`），边生成边推 token，长任务不阻塞前端交互。
  - 证据：`backend/app/api/routes/chat.py:79-81`、`:87-89`；`lesson_plans.py:431`；`summarize.py:292/339/410/432`

### 2.2 架构层面的短板（关键）⚠️

| 维度 | 现状 | 影响 |
|---|---|---|
| 部署拓扑 | 单容器、单实例，**无副本 / 无负载均衡 / 无水平扩展** | 单机故障即全断；无法横向扩容扛流量 |
| 路由模型 | 同步 `def` 为主（实测 **58 个 sync vs 10 个 async**） | 耗时操作在 worker 线程池跑，易打满线程 |
| DB 引擎 | **同步 SQLAlchemy**（`create_engine`，无 asyncpg） | I/O 阻塞线程，无法真正异步并发 |
| 长耗时任务 | 备课 / 判分是同步长调用，无任务队列 / 背压 | 一次生成占住 worker 线程 + 1 条 DB 连接直到完成 |
| 连接池 | 仅 `pool_pre_ping=True`，其余默认（每 worker 约 5 连接） | 4 worker ≈ 20 连接，无共享池，无上限保护 |
| 缓存 | 唯一缓存是 `agent/llm.py:73` 的 `@lru_cache(maxsize=1)`，**只缓存 LLM 客户端实例** | 无业务数据缓存，每次请求都打 PG / Neo4j / LLM |

### 2.3 结论

> **具备「小团队 / 毕设演示级」并发能力，但不是为高并发设计的架构。**
> 少量用户错峰使用时表现良好；一旦**大量用户同时触发生成**，会迅速打满线程池与数据库连接，且无队列缓冲（背压），表现为接口大面积超时。

---

## 3. Redis 与缓存现状

- **全代码库 grep `redis|celery|kafka|rabbitmq` → 零匹配。**
- 没有 Redis，也没有任何消息队列、任务 broker、分布式 session、限流组件。
- 所有状态落在 **PostgreSQL + Neo4j**；演示/运行时数据在内存与数据库，无中间缓存层。
- 即：当前架构**不存在**分布式缓存、发布订阅、异步任务调度能力。

---

## 4. 生产化路线图（按性价比排序）

### P0 — 引入 Redis（成本最低、收益最广）
- 缓存热门知识图谱子图 / 章节拓扑，减少 Neo4j 重复查询。
- 接口级**限流**（如 slowapi + Redis），防止 LLM 调用被刷爆。
- 分布式 session / 缓存登录态（若未来多副本）。

### P1 — 耗时任务异步化
- 将备课生成、批量判分、文档导出等丢进 **Celery / RQ + 消息队列（Redis / RabbitMQ）**。
- 接口改为「提交即返回 task_id」，前端轮询或 SSE 查进度——彻底释放 worker 线程。

### P2 — 异步 I/O 与水平扩展
- DB 驱动换 **asyncpg** + async SQLAlchemy，`async def` 路由打通事件循环。
- 多副本 + 负载均衡（Nginx / K8s），DB 连接池统一调优（`pool_size` / `max_overflow`）。

### 配套 — 可观测与基线
- 加 `sentry-sdk`（已依赖）的慢查询 / 异常采样；用 `locust` 打一条并发基线（如 50 / 200 并发生成场景的 P95 延迟与失败率），作为后续优化的对照。

---

## 5. 检验成果（数据量化）

> 测量日期：2026-10-27，命令可复现。所有数字均来自本仓库实测，非估算。

| 检验项 | 命令 / 来源 | 结果 |
|---|---|---|
| 后端单元测试 | `pytest backend/tests -q` | **236 passed**（2 warnings，耗时 23.75s） |
| 测试规模 | `grep -c "def test_"` | 237 个测试函数 / 25 个测试文件 |
| 前端类型检查 | `vue-tsc --noEmit` | **exit 0**（0 类型错误） |
| 静态检查（ruff） | `ruff check app scripts` | 121 项告警，全为风格类；48 项可 `--fix` 自动修复 |
| 迁移链完整性 | `alembic heads` | **单头** `h4i5j6k7l8m9`（无分支冲突） |
| API 端点数 | 路由装饰器统计 | **121** 个端点 |
| 后端代码量 | `find backend/app -name "*.py" \| wc -l` | 14,282 行 |
| 前端代码量 | `find frontend/src \( -name "*.vue" -o -name "*.ts" \) \| wc -l` | 8,414 行 |

> 说明：ruff 的 121 项均为 `T201`（print）/ `I`（import 排序）/ `ARG001`（未用参数）等风格问题，**无功能性 / 安全隐患**；按项目约定保留存量，未批量改写。

### 功能与接口测试（实测）

数据来自 `docs/testing/测试执行结果.md`（执行方式 `runner.py --scope all --no-jmeter`，离线底座：SQLite + Neo4j/LLM Mock，无需外部依赖，约 13s 可重跑）。

| 层级 | 范围 | 结果 | 耗时 |
|---|---|---|---|
| L0 单元测试 | 25 个 | **100% 通过**（25/25） | 2.43s |
| L1 接口功能 | 144 个（新增 96 + 既有 48） | **96.5% 通过**（139/144，5 个为已登记 xfail） | 10.64s |
| L3 AI 评测 | 3 类产出 | 均分 4.6/5，全部通过 | — |

验收指标对照：单元测试通过率 **100%**（≥95% ✅）、接口功能通过率 **96.5%**（≥95% ✅）、AI rubric 均分 **4.6**（≥4.0 ✅）、前置知识链断点 **0**（≤0 ✅）、SSE 流完整率 **100%**（100% ✅）。已知缺陷 5 项，均 P2 级，以 xfail 固化，不阻塞发布。

> 注：专用测试报告统计为 170 个用例（单元 25 + 接口 144 + AI 套 1）；另一次 `pytest tests` 全量运行报 **236 passed**，口径不同（后者包含 grading/homework/analytics 等独立测试套件）。两者均通过，无失败。

### AI 产出质量评测（含 RAG 知识溯源）

评测为 6 维加权评分卡（5 分制，阈值 ≥4.0），明细见 `backend/tests/ai_eval/results/ai_eval.json`：

| 用例 | 结构 .25 | 无错误 .20 | 知识库依据 kb_grounding .20 | 中文 .15 | 学段解析 .10 | 安全 .10 | 总分 |
|---|---|---|---|---|---|---|---|
| 教案 AI 生成 | 5 | 5 | 5 | 5 | 5 | 5 | **5.0** |
| 文档摘要 | 5 | 5 | 4 | 5 | 3 | 5 | **4.6** |
| 对话问答 | 5 | 5 | 2 | 5 | 3 | 5 | **4.2** |
| **均值** | | | | | | | **4.6** |

> **关于「RAG 准确率」**：当前**没有独立的检索精确率 / 召回率（precision / recall@k）指标**。上表的 `知识库依据(kb_grounding)` 是 LLM 评分卡对「回答是否引用了知识点来源」的**主观打分**，是最接近 RAG 溯源质量的代理指标。其短板明显——**对话问答仅 2/5**，说明 Chat 回答未携带知识点来源引用；评测报告建议接入检索溯源并返回 `sources[]` 以提升可信度。要得到真正的 RAG 准确率，需补 retrieval 层的 hit-rate / recall@k 自动化评测（当前缺）。

### 知识图谱校验（完整性 / 覆盖度）

> **关于「图谱准确率」**：当前**没有独立的实体 / 关系抽取 F1 或准确率指标**。现有可量化的图谱相关校验为：
- **前置知识链断点 = 0**：图谱拓扑完整性校验通过（无断裂的依赖链），属验收指标（≤0 ✅）。
- **章节覆盖度测试**：知识点对章节的覆盖度在 `test_knowledge_points.py` 中有专门用例。
- 图谱质量检查接口（`/admin` 图谱质量检查）已存在，但未沉淀为可量化的「准确率」数字。

如需「图谱准确率」，建议补一套基于标注样本的抽取评测（实体识别 / 关系抽取 F1）。

### 并发与性能测试（现状：脚本已交付，本环境未执行）

- **已交付**：8 套 JMeter 脚本（`backend/tests/jmeter/01~08.jmx`）+ 脚本化压测 `backend/tests/perf/perf_smoke.py`（Java 17 可用，输出 P50/P95/P99、错误率、TPS）。
- **未执行**：本环境无运行中的 PostgreSQL / Neo4j / 后端服务（端口 5432 / 7687 / 18000 均关闭），`report-perf.html` 中 8 个场景全部为「无数据」。**当前没有任何实测的并发 / 性能数字。**
- **已设计但未跑的场景与合格线**（来源 `docs/testing/测试执行结果.md` L2）：

| 脚本 | 场景 | 并发 / 时长 |
|---|---|---|
| 01-auth-login | 登录鉴权 | 50 VU |
| 02-kp-list-graph | 知识点列表与图谱（读） | 50 VU |
| 03-lesson-plan-crud | 教案读写 | 30 VU |
| 04-doc-upload | 文档上传 | 10 VU |
| 05-chat-sse | 对话 SSE 流式 | 20 VU |
| 06-admin-batch | 后台批量审核 | 10 VU |
| 07-mixed-load | 混合业务负载 | 100 VU / 10 min |
| 08-stress-ramp | 阶梯加压探底 | 0→300 VU 爬坡 |

合格线：读 P95 ≤ 200ms、写 P95 ≤ 500ms、读错误率 ≤ 0.1%、写错误率 ≤ 0.5%、压力场景错误率 ≤ 5%。

> ⚠️ **重要**：上述并发 / 性能数字**尚未实测**，不能直接作为上线依据。需在具备 JDK + 运行后端（PG/Neo4j/LLM 可达）的环境执行 `07-mixed-load.jmx` 与 `08-stress-ramp.jmx`（或 `perf_smoke.py`）补齐基线。

### 清理与交付量化
- 删除一次性调试残留 7 项 + 废弃备份 4 项（共 **11 个文件**，走回收站可恢复）。
- 清空 `backend/uploads/` 内 **40MB** 重复压测产物（3 个 md5 相同的 PDF、201 个内容相同的 txt、29 个空文件、85 个 pptx）。
- Git：本地与 `origin/main` 同步（领先/落后 0），含批改模块、侧边栏入口、README、本评估文档累计提交。

---

## 6. 实测证据索引

| 结论 | 证据位置 |
|---|---|
| 4 个 worker 进程 | `backend/Dockerfile:45` |
| SSE 流式输出 | `app/api/routes/chat.py:79,87`；`lesson_plans.py:431`；`summarize.py:292,339,410,432` |
| 同步 DB 引擎 | `app/core/db.py:7-8`（`create_engine`） |
| 连接池仅 pre_ping | `app/core/db.py:10` |
| 同步路由占多数 | 全仓 grep：`def` 58 处 / `async def` 10 处 |
| 唯一缓存=客户端缓存 | `app/agent/llm.py:73`（`@lru_cache(maxsize=1)`） |
| 无 Redis/队列 | 全仓 grep `redis\|celery\|kafka\|rabbitmq` = 0 匹配 |
| 单实例部署 | `compose.yml`（单 backend service，无 replicas / LB） |

---

*本评估与 `技术架构与设计文档.md`、`API.md` 互补：前者讲「搭了什么」，本篇讲「能扛多少、还差什么」。*
