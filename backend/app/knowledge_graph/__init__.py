"""知识图谱层 —— Neo4j 是知识图谱的唯一数据源。

节点标签:
- KnowledgePoint: 知识点
- Document:       文档（元数据镜像，用于图谱内溯源）
- LessonPlan:     教案（元数据镜像，用于图谱内溯源）

关系类型:
- PREREQUISITE: 前置知识
- CONTAINS:     包含关系
- RELATED_TO:   相关关系
- MENTIONS:     文档提及知识点
- COVERS:       教案覆盖知识点
"""
from app.knowledge_graph.repository import KnowledgeGraphRepository

__all__ = ["KnowledgeGraphRepository"]
