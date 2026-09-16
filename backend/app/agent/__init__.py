"""LangGraph Agent 层。

以 LangGraph 为编排框架，包含四个图：
- chat_graph:         教学助手 ReAct 问答（Neo4j 图谱检索 + 文档检索工具）
- extraction_graph:   文档 → 知识点/关系抽取 → 写入 Neo4j
- lesson_plan_graph:  基于图谱上下文生成教案
- summarize_graph:    文档概括 + PPT 大纲生成
"""
