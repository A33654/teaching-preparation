# 教师智能备课系统 · Knowledge Graph + LangGraph 智能备课平台

基于 **知识图谱 + AI Agent** 的智能备课系统：教师只需选择章节，系统自动联动知识体系生成教案；管理员通过审核队列维护全局知识图谱，形成「使用 → 反馈 → 补全」的闭环。

## ✨ 核心亮点

- **知识图谱作为底层推理引擎**：Neo4j 存储知识点/考点/误区三类实体与 7 类关系（前置双向维护、平行、包含），教师端不暴露图结构——章节选择后自动计算输出「本节备课参考」业务清单（教学顺序拓扑排序、重难点、递归前置链、考纲、误区）
- **LangGraph 固定编排备课流水线**：图谱子图查询 → RAG 教材检索 → LLM 生成初稿 → **规则自检（缺失知识点/未覆盖考纲/遗漏前置/顺序风险）**，一键产出「教案 + 结构化校验报告」
- **增量图谱补全闭环**：文档分块抽取（标题切分+重叠+上下文超限自动降级重试）→ 候选队列 → 管理员批量审核（按工单类型分发写图）→ 教师使用中提交纠错/误区/考点建议工单 → 再审核
- **工程健壮性**：多 Provider 三级降级（Qwen→DeepSeek→Kimi 启动探测）、SSE 真流式（custom 流 + values 兜底）、图谱质量检测（非法环/孤立节点/核心缺前置）、401/403 语义分离、全局按名去重

## 🏗 技术架构

```
Vue3 + TS + Element Plus（教师端 5 页 / 管理端 4 页，角色隔离）
        │  HTTP /api/v1 · SSE（token/tool_result/done/error）
FastAPI + LangGraph（chat ReAct · 备课固定流水线 · 抽取图 · PPT 图）
        │  SQLModel/Alembic          │  纯 Cypher（无 APOC）
PostgreSQL 18（业务数据+审核队列）   Neo4j 5.26（知识图谱）
```

**LLM**：LangChain `ChatOpenAI` 统一接入 OpenAI 兼容接口（千问/DeepSeek/Kimi），结构化输出统一 `function_calling` 模式（实测规避 json_schema 400）。

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 · TypeScript · Vite 7 · Element Plus · Pinia · marked |
| 后端 | FastAPI · SQLModel · PostgreSQL 18 · Alembic · JWT · uv |
| AI | LangGraph 1.2 · LangChain · 函数调用 · SSE 流式 · 多 Provider 降级 |
| 图谱 | Neo4j 5.26 · 纯 Cypher · 双向关系维护 · 全局去重 · 质量检测 |
| 部署 | Docker Compose（含 prestart 迁移）· 原生部署脚本（WSL + 启动脚本） |

## 📦 快速开始

### 方式一：Docker Compose（推荐）

```bash
cp .env.example .env   # 填入 LLM API Key（Qwen/DeepSeek 任一）
docker compose up -d --build
# 前端 http://localhost:8080 | 后端文档 http://localhost:18000/docs
# 首次启动 prestart 容器自动执行数据库迁移 + 创建管理员账号
```

### 方式二：原生环境

```bash
# 1. PostgreSQL（原生）
pg_ctl -D E:/work/pgsql/data start
# 2. Neo4j（WSL Ubuntu，脚本自动拉起并同步 IP 到 .env）
bash scripts/start-neo4j-wsl.sh
# 3. 后端
cd backend && uv run alembic upgrade head && uv run python app/initial_data.py && uv run fastapi run app/main.py --reload
# 4. 前端
cd frontend && npm install && npm run dev   # http://localhost:5173
```

**演示账号**（.env 可配）：

| 角色 | 账号 | 密码 |
|---|---|---|
| 教师 | teacher@example.com | teacher123456 |
| 管理员 | admin@example.com | admin123456 |

## 🎯 功能模块

**教师端**：工作台（项目卡片+完整度横幅）→ 智能备课工作台（章节驱动 + 本节备课参考只读面板 + 4 类图谱共建建议工单）→ 教案编辑（Markdown 双栏 + 校验报告 + 底部润色助手 + Word 导出）→ 素材库 → PPT 生成（三套风格模板）

**管理端**：统计看板 → 待审核队列（LLM 候选 + 教师建议两源聚合、批量通过/驳回、按类型分发写图）→ 知识库管理（学科/考点/误区维护 + SVG 图谱可视化 + 批量导入教材）→ 系统日志

## 🗂 目录结构

```
backend/
  app/agent/            # LangGraph 图 + LLM 接入 + 工具（ReAct/备课流水线/抽取/PPT）
  app/knowledge_graph/  # Neo4j 仓储层（纯 Cypher）
  app/api/routes/       # FastAPI 路由（含 admin 审核队列）
  app/alembic/          # 数据库迁移
frontend/
  src/views/            # 教师端页面 + admin/ 管理端页面
  src/api/              # axios 封装 + SSE + authorizedFetch
compose.yml             # Docker Compose（端口偏移版，避开本机开发端口）
scripts/start-neo4j-wsl.sh  # Neo4j 启动 + IP 自动同步
```

## 📄 其他

- 详细技术说明见 `docs/`（环境部署、图谱 Schema、流水线设计）
- LLM 请求经 OpenAI 兼容接口，Key 通过环境变量注入（`.env` 不入库）
