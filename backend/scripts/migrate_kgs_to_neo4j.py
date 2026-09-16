"""数据迁移：PostgreSQL 知识点/关系 → Neo4j（在 alembic upgrade 前运行一次）。

用法（backend 目录下）:
    python -m scripts.migrate_kgs_to_neo4j

先决条件:
- 旧表（knowledgepoint/knowledgerelation）仍存在
- Neo4j 已启动且 .env 配置正确
"""
import sys
from pathlib import Path

# 保证 app 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, create_engine, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.knowledge_graph import KnowledgeGraphRepository  # noqa: E402

# 迁移前旧版 SQL 模型（知识图谱表将被删除，这里内联最小定义）
from sqlmodel import Field, SQLModel  # noqa: E402
import uuid as _uuid  # noqa: E402


class OldKnowledgePoint(SQLModel, table=True):
    __tablename__ = "knowledgepoint"
    id: _uuid.UUID = Field(default_factory=_uuid.uuid4, primary_key=True)
    name: str
    description: str | None = None
    subject: str
    grade_level: str | None = None
    difficulty: int = 1
    is_key_point: bool = False
    owner_id: _uuid.UUID


class OldKnowledgeRelation(SQLModel, table=True):
    __tablename__ = "knowledgerelation"
    id: _uuid.UUID = Field(default_factory=_uuid.uuid4, primary_key=True)
    source_id: _uuid.UUID
    target_id: _uuid.UUID
    relation_type: str


def main() -> None:
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    repo = KnowledgeGraphRepository()

    with Session(engine) as session:
        kps = session.exec(select(OldKnowledgePoint)).all()
        rels = session.exec(select(OldKnowledgeRelation)).all()
        print(f"待迁移: {len(kps)} 个知识点, {len(rels)} 条关系")

        for kp in kps:
            # 复用原 ID，保证教案/文档引用不失效
            existing = repo.get_knowledge_point(str(kp.id))
            if existing:
                continue
            repo._run(
                """
                CREATE (kp:KnowledgePoint {
                    id: $id, name: $name, subject: $subject, description: $description,
                    grade_level: $grade_level, difficulty: $difficulty,
                    is_key_point: $is_key_point, owner_id: $owner_id, created_at: $created_at
                })
                """,
                id=str(kp.id),
                name=kp.name,
                subject=kp.subject,
                description=kp.description or "",
                grade_level=kp.grade_level,
                difficulty=kp.difficulty,
                is_key_point=kp.is_key_point,
                owner_id=str(kp.owner_id),
                created_at=str(kp.created_at or ""),
            )
        print(f"知识点迁移完成: {len(kps)}")

        rel_type_map = {
            "PREREQUISITE": "prerequisite",
            "CONTAINS": "contains",
            "RELATED": "related_to",
            "related_to": "related_to",
            "prerequisite": "prerequisite",
            "contains": "contains",
        }
        count = 0
        for rel in rels:
            rel_type = rel_type_map.get(str(rel.relation_type), "related_to")
            if repo.create_relation(str(rel.source_id), str(rel.target_id), rel_type):
                count += 1
        print(f"关系迁移完成: {count}/{len(rels)}")

        # 教案/文档关联（M2M 表 → 新 JSON 列，由 alembic 迁移前的列更新完成）
        print("迁移完成。请确认无误后执行: alembic upgrade head")


if __name__ == "__main__":
    main()
