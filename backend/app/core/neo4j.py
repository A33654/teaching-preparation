"""Neo4j 驱动单例管理。

知识图谱的所有查询逻辑在 app/knowledge_graph/repository.py 中，
本模块只负责驱动的创建、复用与关闭。
"""
from app.core.config import settings

try:
    from neo4j import Driver, GraphDatabase

    _neo4j_available = True
except ImportError:  # pragma: no cover
    _neo4j_available = False
    GraphDatabase = None  # type: ignore
    Driver = None  # type: ignore

_driver: "Driver | None" = None


def get_neo4j_driver() -> "Driver":
    """获取 Neo4j 驱动单例"""
    if not _neo4j_available:
        raise RuntimeError("neo4j 驱动未安装，请运行: pip install neo4j")
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            # 连接自愈：容器重启/网络抖动后自动重建失效连接
            max_connection_lifetime=1800,
            keep_alive=True,
        )
    return _driver


def close_neo4j_driver() -> None:
    """关闭 Neo4j 驱动"""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def init_neo4j_constraints(driver: "Driver") -> None:
    """初始化 Neo4j 约束和索引（幂等）"""
    statements = [
        # 知识点唯一约束
        "CREATE CONSTRAINT knowledge_point_id IF NOT EXISTS FOR (kp:KnowledgePoint) REQUIRE kp.id IS UNIQUE",
        # 知识点名称索引
        "CREATE INDEX knowledge_point_name IF NOT EXISTS FOR (kp:KnowledgePoint) ON (kp.name)",
        # 文档节点唯一约束
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        # 教案节点唯一约束
        "CREATE CONSTRAINT lesson_plan_id IF NOT EXISTS FOR (lp:LessonPlan) REQUIRE lp.id IS UNIQUE",
        # 考点实体唯一约束
        "CREATE CONSTRAINT exam_point_id IF NOT EXISTS FOR (e:ExamPoint) REQUIRE e.id IS UNIQUE",
        # 误区实体唯一约束
        "CREATE CONSTRAINT misconception_id IF NOT EXISTS FOR (m:Misconception) REQUIRE m.id IS UNIQUE",
    ]
    with driver.session(database=settings.NEO4J_DATABASE) as session:
        for stmt in statements:
            session.run(stmt)
