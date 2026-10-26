# 教师智能备课系统 · 后端接口文档（API Reference）

> 项目：知识图谱 + AI Agent 智能备课平台（FastAPI + LangGraph + Neo4j + PostgreSQL）
> 文档生成日期：2026-09-21
> 接口总数：约 75 个端点（含 1 个 SSE 流式端点、1 个 local 调试端点）

---

## 0. 通用约定

### 0.1 Base URL

所有接口前缀为 `/api/v1`（由 `settings.API_V1_STR` 决定）。生产/本地示例：

```
http://localhost:18000/api/v1
```

自动交互式文档（Swagger UI / OpenAPI）：

```
http://localhost:18000/docs
http://localhost:18000/api/v1/openapi.json
```

### 0.2 认证（Bearer JWT）

除 `POST /login/access-token`、`POST /users/signup`、`GET /utils/health-check/` 外，所有端点都需要在请求头携带：

```
Authorization: Bearer <access_token>
```

- 登录：`POST /login/access-token` 用 `application/x-www-form-urlencoded` 表单提交 `username`（邮箱）、`password`，返回 `access_token`。
- **401**：token 缺失 / 失效 / 用户不存在 / 用户被禁用 → 前端据此清除 token 并跳转登录页。
- **403**：token 有效但权限不足（非超级管理员访问管理端点、或访问他人私有资源）→ 前端提示业务拒绝原因。
- **400**：业务校验失败（如邮箱已存在、密码错误、参数非法）。

### 0.3 统一响应结构

- 列表类接口统一返回 `{ "data": [...], "count": <int> }`。
- 简单操作（删除等）返回 `{ "message": "..." }`。
- 错误统一返回 `{ "detail": "..." }`。
- 分页参数：`skip`（偏移，默认 0）、`limit`（条数，默认 100）。

### 0.4 鉴权角色

- **教师（普通用户）**：仅能访问/修改自己的资源（教案、文档、PPT、课程表、任务、建议工单）。
- **管理员（超级管理员 `is_superuser=true`）**：可访问 `/admin/*` 全部端点，可见全局数据，审核候选知识点与建议工单。
- **local 调试端点** `/private/*`：仅当 `ENVIRONMENT=local` 时挂载，生产环境不存在。

### 0.5 数据流说明

- **业务数据**（用户、教案、文档、PPT、课程表、任务、课标教材、待审核队列、日志）存于 **PostgreSQL**。
- **知识图谱**（知识点、关系、考点、误区）存于 **Neo4j**；相关接口返回体的 `knowledge_points` 等字段是从 Neo4j 按 ID 实时拉取组装的。Neo4j 不可用时绝大部分业务降级为空数组/ 404，不会整体 500。
- **AI 生成**（教案、概括、PPT 大纲、问答）走 **LangGraph**；耗时操作（文档抽取）在后台任务执行，前端按资源 `status` 轮询进度。

---

## 1. 认证模块 `login`

### 1.1 `POST /login/access-token`
OAuth2 兼容登录，获取 access token。

- **Auth**：无
- **Content-Type**：`application/x-www-form-urlencoded`
- **Body 字段**：`username`（邮箱）、`password`
- **Response `200`** `Token`：

```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

- **Error**：`400` 邮箱或密码错误 / 用户未激活。

### 1.2 `POST /login/test-token`
用当前 token 换取当前用户信息（校验 token 是否有效）。

- **Auth**：Bearer
- **Response `200`** `UserPublic`（见 §2.3）。

### 1.3 `POST /password-recovery/{email}`
发起密码重置（出于防枚举，无论邮箱是否存在都返回相同消息）。

- **Auth**：无
- **Response `200`** `Message`。

### 1.4 `POST /reset-password/`
用重置 token 设置新密码。

- **Auth**：无
- **Body** `NewPassword`：`{ "token": "...", "new_password": "..." }`
- **Response `200`** `Message`。`400` token 无效。

### 1.5 `POST /password-recovery-html-content/{email}`
返回密码重置邮件的 HTML 内容（仅超级管理员，用于预览）。

- **Auth**：超级管理员
- **Response `200`**：`text/html`。

---

## 2. 用户模块 `users`

### 2.1 `GET /users/`
用户列表（超级管理员）。

- **Auth**：超级管理员
- **Query**：`skip`、`limit`
- **Response `200`** `UsersPublic`。

### 2.2 `POST /users/`
创建用户（超级管理员）。`400` 邮箱已存在。

- **Auth**：超级管理员
- **Body** `UserCreate`：`email`、`password`（≥8）、`full_name`、可选 `is_superuser`、`subject`、`grade_level`、`school` 等。

### 2.3 `GET /users/me`
获取当前登录用户。

- **Auth**：Bearer
- **Response `200`** `UserPublic`：

```json
{
  "id": "uuid", "email": "t@e.com", "full_name": "张老师",
  "nickname": null, "bio": null, "phone": null, "avatar_url": null,
  "subject": "数学", "grade_level": "高中", "school": null,
  "is_active": true, "is_superuser": false, "created_at": "2026-09-21T..."
}
```

### 2.4 `PATCH /users/me`
更新当前用户信息（邮箱、昵称、简介、电话、头像、学科、学段、学校）。

- **Auth**：Bearer
- **Body** `UserUpdateMe`。`409` 邮箱被他人占用。

### 2.5 `PATCH /users/me/password`
修改当前用户密码。

- **Auth**：Bearer
- **Body** `UpdatePassword`：`{ "current_password": "...", "new_password": "..." }`
- **Error**：`400` 当前密码错误 / 新旧密码相同。

### 2.6 `DELETE /users/me`
删除当前用户（超级管理员禁止自助删除）。

- **Auth**：Bearer
- **Error**：`403` 超级管理员不可删除自己。

### 2.7 `POST /users/signup`
公开注册（无需登录）。

- **Auth**：无
- **Body** `UserRegister`：`email`、`password`、`full_name?`。

### 2.8 `GET /users/{user_id}`
按 ID 获取用户。本人可看；他人仅超级管理员可见。`403`/`404`。

- **Auth**：Bearer

### 2.9 `PATCH /users/{user_id}`
更新指定用户（超级管理员）。`404` 用户不存在；`409` 邮箱冲突。

### 2.10 `DELETE /users/{user_id}`
删除指定用户（超级管理员；不可删除自己）。同时级联删除其 Item。

---

## 3. 通用 Item 模块 `items`

> 脚手架保留模块（通用示例数据），与备课主流程无关，权限规则同用户私有资源。

| 方法 | 路径 | Auth | 说明 |
|---|---|---|---|
| GET | `/items/` | 用户（超管看全部） | 列表 `ItemsPublic` |
| GET | `/items/{id}` | 用户（属主/超管） | 详情 `ItemPublic` |
| POST | `/items/` | 用户 | 创建 |
| PUT | `/items/{id}` | 用户（属主/超管） | 更新 |
| DELETE | `/items/{id}` | 用户（属主/超管） | 删除 |

`ItemCreate/Update`：`title`（必填）、`description?`。

---

## 4. 知识图谱模块 `knowledge-points`（数据源：Neo4j）

> 知识点与关系均存于 Neo4j。关系类型 `relation_type` 取值：`prerequisite`（前置）、`contains`（包含）、`related_to`（相关）。考点/误区为挂载在知识点下的实体节点。

### 4.1 `GET /knowledge-points/graph/full`
获取当前用户（超管为全局）所有知识点及关系的全图。

- **Auth**：Bearer
- **Response `200`** `SubgraphResponse`：`{ "nodes": [...], "edges": [{source_id,target_id,relation_type}] }`

### 4.2 `GET /knowledge-points/`
知识点列表，支持筛选与搜索。

- **Query**：`skip`、`limit`、`subject?`、`grade_level?`、`search?`
- **Response `200`** `KnowledgePointsPublic`。

### 4.3 `GET /knowledge-points/{id}`
单个知识点详情。`404` 不存在；`403` 无权访问。

### 4.4 `POST /knowledge-points/`
创建知识点（写入 Neo4j）。

- **Body** `KnowledgePointCreate`：`name`、`subject`（默认"通用"）、`description?`、`grade_level?`（小学/初中/高中）、`difficulty?`（1-5）、`is_key_point?`。

### 4.5 `PUT /knowledge-points/{id}`
更新知识点属性。权限同上。

### 4.6 `DELETE /knowledge-points/{id}`
删除知识点（Neo4j `DETACH DELETE`，级联删除关系）。返回 `{ "message": "知识点已删除" }`。

### 4.7 `POST /knowledge-points/{id}/relations`
为知识点创建关系（出边）。目标知识点须存在且属主一致。

- **Body** `KnowledgeRelationCreate`：`target_id`、`relation_type`（默认 `related_to`）。
- **Response `200`** `KnowledgeRelationOut`。

### 4.8 `GET /knowledge-points/{id}/relations`
获取某知识点的全部关系（出边 + 入边）。

### 4.9 `DELETE /knowledge-points/{id}/relations`
删除关系。

- **Query**：`target_id`（必填）、`relation_type`（默认 `related_to`）。

### 4.10 `GET /knowledge-points/{id}/subgraph`
以某知识点为中心的子图（变长路径遍历）。

- **Query**：`depth`（默认 2）→ `SubgraphResponse`。

### 4.11 `POST /knowledge-points/search`
自然语言关键词搜索知识图谱节点。

- **Body**：`{ "query": "...", "top_k": 10 }` → `{ "query", "results": [...] }`。

### 4.12 `POST /knowledge-points/chapter-context`
**章节自动联动核心接口**：教师选章节后，自动检索本章知识点并补充前置依赖、考点、误区，计算知识库完整度，并产出备课业务清单（教学顺序拓扑排序 / 重难点 / 递归前置链）。

- **Body** `{ "chapter": "...", "subject": "" }`
- **Response `200`**：

```json
{
  "chapter": "第三章 函数",
  "knowledge_points": [ { "id","name","prerequisites":[],"exam_points":[],"misconceptions":[] } ],
  "coverage": "complete | partial | missing",
  "message": "知识库完整（核心知识点覆盖 8/9）...",
  "teaching_order": ["概念A","概念B",...],
  "key_difficult_points": [ { "name":"...", "reasons":["核心考点","难度 4/5"] } ],
  "prerequisite_chain": [ { "name":"...", "depth":1 } ]
}
```

### 4.13 考点实体（考纲：了解 / 理解 / 掌握）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/knowledge-points/{id}/exam-points` | 列出关联考点 `{ "data": [...] }` |
| POST | `/knowledge-points/{id}/exam-points` | 新增考点 Body：`{ "name", "level":"理解", "description":"" }` |
| DELETE | `/knowledge-points/{id}/exam-points/{exam_id}` | 删除考点 |

### 4.14 误区实体（学生常见错误概念）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/knowledge-points/{id}/misconceptions` | 列出误区 `{ "data": [...] }` |
| POST | `/knowledge-points/{id}/misconceptions` | 新增误区 Body：`{ "content", "correction":"" }` |
| DELETE | `/knowledge-points/{id}/misconceptions/{mis_id}` | 删除误区 |

---

## 5. 教案模块 `lesson-plans`（AI 走 LangGraph 教案图）

### 5.1 `GET /lesson-plans/`
教案列表。超管看全部；教师看自己。`{ "data": [LessonPlanPublic], "count" }`。

`LessonPlanPublic` 含：`id`、`title`、`subject`、`grade_level`、`teaching_objectives`、`teaching_process`、`owner_id`、`subject_id?`、`created_at`、`knowledge_point_ids`、`knowledge_points`（从 Neo4j 组装的 `KnowledgePointOut[]`）。

### 5.2 `POST /lesson-plans/summarize`
**上传文档 → LangGraph 概括图**，返回摘要/主题/建议教法。

- **Content-Type**：`multipart/form-data`，字段 `file`（PDF/DOCX/TXT）。
- **Response `200`** `SummarizeResponse`：`{ "summary", "key_topics":[], "suggested_approach" }`。

### 5.3 `POST /lesson-plans/ai-generate`
**章节驱动的一键教案生成**（核心 AI 能力）。

- **Auth**：Bearer
- **Body** `AILessonPlanRequest`：

```json
{
  "knowledge_point_ids": [],   // 可手动指定；为空时按 chapter 自动检索
  "subject": "数学",
  "grade_level": "高中",
  "extra_context": "",
  "style": "标准",
  "requirements": "",
  "summary_text": "",
  "chapter": "第三章 函数"   // 提供时自动从知识图谱检索本章知识点
}
```

- **Response `200`** `GenerateResponse`：

```json
{
  "id": "uuid", "title": "...", "subject": "数学", "grade_level": "高中",
  "teaching_objectives": "Markdown...", "teaching_process": "Markdown...",
  "key_points": [], "difficult_points": [],
  "graph_context": [], "raw_text": "# ...", "verification_report": { }
}
```

- 图谱命中 → 基于图谱结构生成；图谱缺失 → 自动 RAG 兜底，并在说明中标注知识库状态。
- **Error**：`500` 生成失败（返回具体原因）。

### 5.4 `GET /lesson-plans/{id}`
教案详情（组装知识点）。`404`/`403`。

### 5.5 `POST /lesson-plans/`
手动创建教案（不走 AI）。

- **Body** `LessonPlanCreate`：`title`、`subject`、`grade_level?`、`teaching_objectives?`、`teaching_process?`、`knowledge_point_ids?`、`subject_id?`。

### 5.6 `PUT /lesson-plans/{id}`
更新教案。支持更新 `knowledge_point_ids`（同步 Neo4j `COVERS` 关系）。

### 5.7 `DELETE /lesson-plans/{id}`
删除教案。`404`/`403`。

### 5.8 `GET /lesson-plans/{id}/export`
导出教案为 **Word（.docx）** 文件下载（`application/vnd.openxmlformats-officedocument.wordprocessingml.document`）。`404`/`403`。

---

## 6. 文档模块 `documents`（上传解析 + LangGraph 抽取写入图谱）

### 6.1 `GET /documents/`
文档列表，批量预取知识点（Neo4j 故障时降级为空）。`DocumentsPublic`。

`DocumentPublic` 含：`id`、`filename`、`original_filename`、`file_type`、`file_size`、`status`、`error_message?`、`created_at`、`owner_id`、`extracted_text?`（截断 500 字）、`summary?`、`subject_id?`、`knowledge_point_ids`、`knowledge_points`。

`status` 取值：`uploaded` → `parsing`/`analyzing` → `completed` / `failed`。

### 6.2 `GET /documents/{id}`
文档详情。`403`/`404`。

### 6.3 `GET /documents/{id}/file`
下载原始文件（素材库预览）。`404` 文件已丢失 / 无权限。

### 6.4 `DELETE /documents/{id}`
删除文档及其磁盘文件。`403`/`404`。

### 6.5 `POST /documents/upload`
**上传文档并自动解析 + 触发知识抽取**。

- **Content-Type**：`multipart/form-data`，字段 `file`（PDF/DOCX/TXT）、`auto_analyze`（bool，默认 true）。
- 文本解析同步完成立即返回；LangGraph 抽取（LLM 多轮）放入**后台任务**，前端按 `status` 轮询。
- **Error**：`400` 不支持的文件类型。
- **Response**：`DocumentPublic`（初始 `status=uploaded` 或解析失败时 `failed`）。

### 6.6 `POST /documents/{id}/analyze`
手动触发知识抽取（对已上传且已解析的文档）。

- **Response `200`**：`{ "document": DocumentPublic, "extraction": { "subject","knowledge_points_count","relations_count","knowledge_points":[],"relations":[],"summary":"" } }`。
- **Error**：`400` 文档尚未解析；`404`/`403`；`500` 抽取失败。

### 6.7 `POST /documents/search`
检索知识图谱节点 + 文档内容（供 AI 助手与前端搜索）。

- **Body**：`{ "query", "top_k":10 }` → `{ "query", "knowledge_points":[], "documents":[{id,filename,snippet}] }`。

---

## 7. AI 教学助手 `chat`（SSE 流式）

### 7.1 `POST /chat/`
RAG 问答：LangGraph ReAct Agent 自主检索知识图谱与文档后回答。

- **Auth**：Bearer
- **Body** `ChatRequest`：`{ "message": "...", "history": [{"role":"user|assistant","content":"..."}], "mode": "sse" | "json" }`。

**SSE 模式（`mode=sse`，默认）**：`text/event-stream`，每条事件为 `data: <JSON>\n\n`：

```json
{ "type": "token", "content": "逐字..." }            // 逐字输出
{ "type": "tool_result", "tool_name": "...", "sources": [...] }  // 工具调用完成
{ "type": "done", "reply": "...", "sources": [...] }  // 结束
{ "type": "error", "content": "..." }                 // 出错
```

**JSON 模式（`mode=json`）**：一次性返回 `ChatResponse`：`{ "reply": "...", "sources": [...] }`。

---

## 8. 课标教材模块 `curriculum`

### 8.1 学科

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/curriculum/subjects` | 我的学科列表 `SubjectsPublic` |
| POST | `/curriculum/subjects` | 创建学科 Body：`{ "name", "description"? }` |
| DELETE | `/curriculum/subjects/{sid}` | 删除学科 `400` 无效ID / `404` |

### 8.2 教材

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/curriculum/textbooks?subject_id=` | 教材列表（可按学科筛选） |
| POST | `/curriculum/textbooks` | 创建教材（自动创建根章节）Body：`name`、`subject_id`、`version?`、`grade_level?`、`cover_url?`、`description?` |
| DELETE | `/curriculum/textbooks/{tid}` | 删除教材 |

### 8.3 章节（树形，章节自动同步为 Neo4j 知识点节点）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/curriculum/chapters/{textbook_id}` | 章节树（扁平转树，`children` 嵌套） |
| POST | `/curriculum/chapters` | 创建章节，自动同步 Neo4j 知识点节点 Body：`title`、`parent_id?`、`textbook_id`、`level` |
| PUT | `/curriculum/chapters/{cid}/reorder` | 调整章节层级/顺序 Query：`new_parent_id?`、`new_order?` |
| PUT | `/curriculum/chapters/{cid}` | 重命名章节（同步 Neo4j 节点名）Query：`title` |
| DELETE | `/curriculum/chapters/{cid}` | 删除章节（同步删除 Neo4j 节点） |

### 8.4 `GET /curriculum/dashboard/{subject_id}`
学科仪表盘：聚合该学科下文档、教案、PPT、知识点。

- **Response `200`**：`{ "subject", "documents":[], "lesson_plans":[], "ppts":[], "knowledge_points":[] }`。

---

## 9. 提醒备忘模块 `reminders`

### 9.1 课程表

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/reminders/schedules` | 我的课程表（按星期/时间排序）`SchedulesPublic` |
| POST | `/reminders/schedules` | 新增课程 Body：`day_of_week`(0-6)、`start_time`(HH:MM)、`end_time`、`subject`、`classroom?` |
| DELETE | `/reminders/schedules/{sid}` | 删除课程 |

### 9.2 学习任务

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/reminders/tasks?show_completed=false` | 任务列表（默认仅未完成）`TasksPublic` |
| POST | `/reminders/tasks` | 新增任务 Body：`title`、`description?`、`due_date?`(YYYY-MM-DD)、`priority?`(high/normal/low) |
| PUT | `/reminders/tasks/{tid}/toggle` | 切换完成状态 `TaskPublic` |
| DELETE | `/reminders/tasks/{tid}` | 删除任务 |

### 9.3 `GET /reminders/today`
今日概览：今日课程 + 临近任务 + 星期名。

- **Response `200`** `TodayOverview`：`{ "today_schedule":[], "upcoming_tasks":[], "day_name":"周一" }`。

---

## 10. 概括 / PPT 模块 `summarize`

### 10.1 `POST /summarize/`
上传文件 → LangGraph 概括图（与 `lesson-plans/summarize` 类似，独立入口）。

- **Content-Type**：`multipart/form-data`，字段 `file` → `SummarizeResponse`。

### 10.2 `POST /summarize/generate-ppt`
上传文件 → LangGraph PPT 大纲图 → 渲染 **PPTX** 下载。

- **Content-Type**：`multipart/form-data`，字段 `file`、`style`（`professional`/`vivid`/`minimal`）、`slide_count`（默认 8）。
- **Response**：`.pptx` 文件流（`application/vnd.openxmlformats-officedocument.presentationml.presentation`）。
- 同时保存 `PptRecord`（标题、风格、页数、slides_json）。

### 10.3 `GET /summarize/ppt-list`
PPT 列表。`PptRecordsPublic`（`data: PptRecordPublic[]`, `count`）。

### 10.4 `GET /summarize/ppt/{ppt_id}`
获取单个 PPT 记录详情（含 `slides_json` 每页要点，供前端编辑/预览复用）。`400` 无效ID / `404` / `403` 非属主。

### 10.5 `PUT /summarize/ppt/{ppt_id}/save`
保存编辑后的 PPT 幻灯片并**重新生成 PPTX** 下载。

- **Body** `SavePptRequest`：`{ "slides": [ {"title","bullets":[]} , ... ], "style": "professional" }`。
- **Response**：更新后的 `.pptx` 文件流。

### 10.6 `GET /summarize/ppt/{ppt_id}/export`
导出（下载）已生成的 PPTX 文件。`404` 文件已删除 / 无权限。

---

## 11. 管理员后台模块 `admin`（超级管理员）

> 审核流：LLM 抽取 / 教师提交 → 候选/建议队列（`pending`）→ 管理员通过 → 写入 Neo4j 图谱。

### 11.1 `GET /admin/stats`
管理看板统计卡片。`AdminStats`：`pending_candidates`、`subjects_count`、`knowledge_points_count`、`documents_total`、`documents_processing`、`documents_failed`。

### 11.2 `GET /admin/candidates`
候选知识点列表（LLM 抽取 + 教师提交聚合）。

- **Query**：`status`（`pending`/`approved`/`rejected`，空=全部）、`skip`、`limit` → `CandidatesPublic`。

### 11.3 `POST /admin/candidates`
教师端提交候选知识点（手动补充缺失知识点）。Body `CandidateCreate`：`name`、`subject?`、`grade_level?`、`textbook_version?`、`definition?`、`prerequisites?`、`kind?`、`target_kp_id?`、`suggestion?`。

### 11.4 `PATCH /admin/candidates/{id}`
管理员编辑候选知识点（超级管理员）。

### 11.5 `POST /admin/candidates/{id}/approve`
审核通过：按 `kind` 分发写入 Neo4j 图谱（合并去重 / 纠错更新 / 误区 / 考点 / 创建节点+前置关系）。返回 `{ "message": "处理摘要" }`。`400` 已处理；`404`；`500` 写入失败。

### 11.6 `POST /admin/candidates/{id}/reject`
驳回候选知识点。

### 11.7 `POST /admin/candidates/batch-approve`
批量审核通过（逐条写入，单条失败不影响其他）。

- **Body**：`{ "ids": ["uuid",...] }` → `{ "approved":[], "approved_count":N, "failed":[{"id","name?","reason"}] }`。

### 11.8 `POST /admin/candidates/batch-reject`
批量驳回 → `{ "rejected_count": N }`。

### 11.9 `GET /admin/graph-quality`
图谱质量检测：循环依赖 / 孤立节点 / 核心知识点缺少前置。返回 `{ "cycles":[], "isolated_nodes":[], "key_points_without_dependencies":[] }`。

### 11.10 `GET /admin/logs`
系统任务日志（抽取失败 / 知识库更新记录）。`ExtractionLogsPublic`。

### 11.11 教师共建建议工单 `knowledge_suggestion`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/admin/suggestions` | 教师提交共建建议工单 Body `SuggestionCreate`：`kind`(missing_kp/correction/misconception/exam_point)、`name`、`subject?`、`grade_level?`、`textbook_version?`、`chapter?`、`target_kp_id?`、`definition?`、`suggestion?` |
| GET | `/admin/suggestions?status=&skip=&limit=` | 建议工单列表（与候选队列在管理端聚合展示） |
| POST | `/admin/suggestions/{id}/approve` | 审核通过：按 kind 分发写入图谱 |
| POST | `/admin/suggestions/{id}/reject` | 驳回建议工单 |

---

## 12. 工具模块 `utils`

| 方法 | 路径 | Auth | 说明 |
|---|---|---|---|
| POST | `/utils/test-email/` | 超级管理员 | 发送测试邮件 `Message` |
| GET | `/utils/health-check/` | 无 | 健康检查，返回 `true` |

---

## 13. 本地调试端点 `private`（仅 `ENVIRONMENT=local`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/private/users/` | 直接创建用户（绕过注册流程，用于本地初始化）Body：`email`、`password`、`full_name`、`is_verified?` |

> 生产环境（`staging`/`production`）不挂载此路由。

---

## 14. 关键数据模型速查

### 14.1 用户 `UserPublic`
`id, email, full_name?, nickname?, bio?, phone?, avatar_url?, subject?, grade_level?, school?, is_active, is_superuser, created_at`

### 14.2 知识点 `KnowledgePointOut`（Neo4j）
`id, name, subject, description?, grade_level?, difficulty(1-5), is_key_point(bool), owner_id?, created_at?`

### 14.3 教案 `LessonPlanPublic`
`id, title, subject, grade_level?, teaching_objectives?, teaching_process?, owner_id, subject_id?, created_at?, knowledge_point_ids[], knowledge_points[KnowledgePointOut]`

### 14.4 文档 `DocumentPublic`
`id, filename, original_filename, file_type, file_size, status, error_message?, created_at?, owner_id, extracted_text?(截断), summary?, subject_id?, knowledge_point_ids[], knowledge_points[]`

### 14.5 候选/建议工单
`id, kind, name, subject, grade_level?, textbook_version?, chapter?, target_kp_id?, definition?, suggestion?, source, status(pending/approved/rejected), submitter_id, created_at?`

### 14.6 PPT 记录 `PptRecordPublic`
`id, title, subject_id?, original_filename, file_size, slide_count, extracted_text?, slides_json?, style?, created_at?, owner_id`

---

## 15. 典型调用流程示例

### 15.1 教师备课主流程
1. `POST /login/access-token` → 拿到 token。
2. `POST /knowledge-points/chapter-context` `{ "chapter": "第三章 函数" }` → 获取本章图谱联动（教学顺序/重难点/完整度）。
3. `POST /lesson-plans/ai-generate` `{ "chapter": "第三章 函数", "subject":"数学", "grade_level":"高中" }` → 一键生成教案（带校验报告）。
4. `GET /lesson-plans/{id}/export` → 导出 Word。
5. 使用中发现知识库缺失 → `POST /admin/suggestions` 提交共建建议工单（管理员后续审核写入图谱）。

### 15.2 文档入库 → 图谱补全闭环
1. `POST /documents/upload` `file=教材.pdf` → 立即返回（status=uploaded）。
2. 轮询 `GET /documents/` 直到 `status=completed`（后台 LangGraph 抽取写入候选队列）。
3. 管理员 `GET /admin/candidates` → `POST /admin/candidates/{id}/approve` 审核通过，写入 Neo4j 图谱。

### 15.3 AI 助手流式问答
```
POST /chat/  { "message":"什么是函数?", "mode":"sse", "history":[] }
→ data: {"type":"token","content":"函数"}
→ data: {"type":"token","content":"是..."}
→ data: {"type":"done","reply":"...","sources":[...]}
```

---

## 16. 已知限制与注意事项

- AI 生成类接口依赖 LLM（Qwen/DeepSeek/Kimi）及 Neo4j/PostgreSQL，缺失相应配置时部分接口会返回 500 或降级。
- 知识图谱接口在 Neo4j 不可用时整体降级，不影响业务表数据读写。
- 文档抽取为后台任务，需前端主动轮询 `status` 感知进度。
- 教师提交的建议/候选工单审核结果不实时推送（按需刷新待审核队列）。
