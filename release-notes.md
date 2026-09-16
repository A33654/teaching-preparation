# 更新日志

## 当前版本

本项目基于 [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) v0.10.0 构建，并进行了以下定制化开发：

### 新增功能

* 🧠 **知识图谱** — 知识点节点管理，支持前置/包含/相关三种关系类型，集成 Neo4j 图数据库
* 📚 **教案管理** — 教案 CRUD，支持关联知识点，含教学目标和教学过程
* 📄 **文档解析** — 上传 PDF / DOCX / PPTX 文件，自动提取文本内容
* 📅 **课程表** — 每周课程安排管理
* ✅ **学习任务** — 待办任务与优先级管理
* 📖 **学科与教材** — 学科 → 教材 → 章节三级树形结构
* 🎯 **PPT 管理** — PPT 文件记录与内容提取
* 🤖 **AI 对话** — 集成千问（Qwen）和 DeepSeek 双大模型
* 📝 **AI 总结** — 文档内容自动总结
* 🔍 **RAG 检索增强生成** — 基于文档的向量检索问答
* 🔔 **提醒功能** — 教学日程提醒

### 技术栈

* 后端：FastAPI + SQLModel + PostgreSQL 18 + Neo4j 5 + Alembic
* 前端：React + TypeScript + Vite + Tailwind CSS + shadcn/ui
* AI：千问 Qwen-Plus + DeepSeek-Chat
* 基础设施：Docker Compose + Traefik + GitHub Actions

---

## 上游模板更新日志

如需查看原始模板的完整更新历史，请访问 [Full Stack FastAPI Template Release Notes](https://github.com/fastapi/full-stack-fastapi-template/blob/master/release-notes.md)。
