# 教师备课系统

基于 **LangGraph + Neo4j + FastAPI + Vue3** 重构的智能教师备课平台，AI Agent 自动从教材文档中抽取知识图谱，支持智能问答、教案生成与 PPT 制作。

## 功能特性

### 核心业务
- 🤖 **AI 教学助手** — LangGraph ReAct Agent 自主检索知识图谱与文档库，SSE 流式问答
- 🧠 **知识图谱** — Neo4j 存储知识点与关系（前置/包含/相关），图谱可视化（vis-network）与子图遍历
- 📄 **文档解析** — 上传 PDF / DOCX / TXT，LangGraph 抽取图自动识别学科、抽取知识点与关系并写入 Neo4j
- 📝 **教案管理** — LangGraph 教案图基于图谱上下文（前置/关联脉络）智能生成教案，支持导出 Word
- 🎬 **PPT 生成** — LangGraph PPT 大纲图生成幻灯片内容，python-pptx 渲染 PPTX
- 🎯 **教材课标** — 学科 → 教材 → 章节树，章节自动同步为 Neo4j 知识点节点
- 📅 **备忘提醒** — 课程表 + 教学任务管理
- 👤 **用户体系** — JWT 认证、角色权限、个人资料、找回密码

### 技术架构
- 🕸️ **LangGraph** — AI Agent 编排框架（ReAct 问答图、知识抽取图、教案生成图、概括图、PPT 大纲图）
- 🗄️ **Neo4j 5** — 知识图谱唯一数据源（纯 Cypher，无 APOC 依赖）
- ⚡ **FastAPI** — Python 后端框架，SSE 流式响应
- 🧰 **SQLModel + PostgreSQL 18** — 用户/文档/教案等业务数据存储
- 🖥️ **Vue 3 + Element Plus** — 前端框架，Pinia + Vue Router + Vite
- 🔌 **Qwen / DeepSeek** — 双大模型（OpenAI 兼容接口，千问优先）
- 🐋 **Docker Compose** — 一键部署

## 项目结构

```
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── agent/               # LangGraph Agent 层
│   │   │   ├── graphs/          #   chat/extraction/lesson_plan/summarize 图
│   │   │   ├── tools/           #   图谱检索 + 文档检索工具
│   │   │   ├── llm.py           #   Qwen/DeepSeek 统一 ChatModel
│   │   │   ├── schemas.py       #   LLM 结构化输出 Schema
│   │   │   └── state.py         #   图状态定义
│   │   ├── knowledge_graph/     # Neo4j 仓储层（知识图谱唯一数据源）
│   │   ├── alembic/             # 数据库迁移（含图谱迁移至 Neo4j 的迁移）
│   │   ├── api/routes/          # API 路由
│   │   ├── core/                # 配置、数据库、安全、Neo4j 驱动
│   │   ├── models.py            # SQLModel 模型（图谱部分为 API Schema）
│   │   └── main.py              # 应用入口
│   ├── scripts/
│   │   └── migrate_kgs_to_neo4j.py  # 旧数据 SQL → Neo4j 迁移脚本
│   └── Dockerfile
├── frontend/                    # Vue 3 + Element Plus 前端
│   ├── src/
│   │   ├── api/                 # axios 客户端 + 类型化 API
│   │   ├── stores/              # Pinia 认证状态
│   │   ├── router/              # Vue Router + 路由守卫
│   │   ├── layouts/             # 侧边栏布局
│   │   └── views/               # 12 个业务页面
│   └── Dockerfile
├── frontend-react.bak/          # 重构前的 React 前端（备份参考）
├── compose.yml                  # Docker Compose（生产）
├── compose.override.yml         # Docker Compose（本地开发）
└── .env.example                 # 环境变量模板
```

## 快速开始

### 环境要求

- Docker 和 Docker Compose，或本地 Python 3.10+ + Node.js 20+ + PostgreSQL 18 + Neo4j 5
- Qwen（千问）或 DeepSeek API Key

### 方式一：Docker Compose（推荐）

```bash
cp .env.example .env   # 填入 LLM API Key 与各密码
docker compose up -d
```

启动后访问：
- 前端页面：`http://localhost:5173`
- 后端 API 文档：`http://localhost:8000/docs`
- Neo4j Browser：`http://localhost:7474`

### 方式二：本地开发

```bash
# 1. 启动数据库容器
docker compose up -d db neo4j

# 2. 后端
cd backend
uv sync
uv run alembic upgrade head
uv run python app/initial_data.py
uv run fastapi run app/main.py --reload

# 3. 前端（另开终端）
cd frontend
npm install
npm run dev   # http://localhost:5173，已配置 /api 代理到 8000
```

## 从旧版本升级（知识图谱迁移）

旧版本知识点/关系存储在 PostgreSQL，新版本以 Neo4j 为唯一数据源：

```bash
# 1. 迁移前：把 PostgreSQL 中的知识点与关系复制到 Neo4j（保留原 UUID）
cd backend
uv run python -m scripts.migrate_kgs_to_neo4j

# 2. 执行迁移（M2M 关联自动回填为 JSON 引用列，随后删除旧表）
uv run alembic upgrade head
```

## 环境配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QWEN_API_KEY` | 千问 API 密钥（主 LLM） | — |
| `QWEN_MODEL` | 千问模型 | `qwen-plus` |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（备用） | — |
| `NEO4J_URI` | Neo4j 连接地址 | `bolt://localhost:7687` |
| `NEO4J_DATABASE` | Neo4j 数据库名 | `neo4j` |
| `AGENT_MAX_ITERATIONS` | ReAct Agent 最大工具轮数 | `8` |
| `POSTGRES_*` | PostgreSQL 连接配置 | — |
| `SECRET_KEY` / `FIRST_SUPERUSER*` | 安全与初始管理员 | — |

> ⚠️ 部署到生产环境前，务必修改 `SECRET_KEY`、`POSTGRES_PASSWORD`、`NEO4J_PASSWORD` 和所有 API 密钥。

## API 路由

| 模块 | 路径前缀 | 说明 |
|------|----------|------|
| AI 问答 | `/api/v1/chat` | LangGraph Agent，SSE 流式（`mode=json` 可非流式） |
| 知识图谱 | `/api/v1/knowledge-points` | Neo4j 知识点/关系 CRUD、全图、子图、搜索 |
| 文档 | `/api/v1/documents` | 上传解析、知识抽取（LangGraph）、搜索 |
| 教案 | `/api/v1/lesson-plans` | CRUD、AI 生成、概括、Word 导出 |
| 概括/PPT | `/api/v1/summarize` | 文档概括、PPT 生成/编辑/导出 |
| 教材课标 | `/api/v1/curriculum` | 学科/教材/章节（自动同步 Neo4j） |
| 提醒 | `/api/v1/reminders` | 课程表、任务、今日概览 |
| 认证/用户 | `/api/v1/login` `/api/v1/users` | JWT 登录、注册、资料 |

## 技术栈

**Agent/LLM**：LangGraph · LangChain · 千问 Qwen-Plus · DeepSeek-Chat

**后端**：Python 3.10+ · FastAPI · SQLModel · PostgreSQL 18 · Neo4j 5 · Alembic · JWT

**前端**：Vue 3 · TypeScript · Vite · Element Plus · Pinia · Vue Router · vis-network

**基础设施**：Docker · Docker Compose · Traefik

---

本项目基于 [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) 构建。

## License

MIT License
