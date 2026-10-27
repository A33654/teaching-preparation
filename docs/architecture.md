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

## 5. 实测证据索引

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
