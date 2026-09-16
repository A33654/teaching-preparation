"""Neo4j 知识图谱仓储层（纯 Cypher，无 APOC 依赖）。

本模块是知识图谱的唯一读写入口，取代原先「PostgreSQL 存储 + Neo4j 镜像」的双写方案。
所有查询均为参数化 Cypher，天然防注入。
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings
from app.core.neo4j import get_neo4j_driver

# 关系类型映射：业务枚举 -> Cypher 关系类型
RELATION_TO_CYPHER = {
    "prerequisite": "PREREQUISITE",
    "prerequisite_for": "PREREQUISITE_FOR",
    "depends_on": "DEPENDS_ON",
    "contains": "CONTAINS",
    "related_to": "RELATED_TO",
    "parallel": "PARALLEL",
    "has_exam_point": "HAS_EXAM_POINT",
    "has_misconception": "HAS_MISCONCEPTION",
}
CYPHER_TO_RELATION = {v: k for k, v in RELATION_TO_CYPHER.items()}

# 知识点-知识点关系（get_relations / get_neighbors 遍历用）
KP_TO_KP_REL_TYPES = ("PREREQUISITE", "PREREQUISITE_FOR", "DEPENDS_ON", "CONTAINS", "RELATED_TO", "PARALLEL")

# 反向关系对：创建正向时自动维护反向（双向索引，避免复杂反向查询）
BIDIRECTIONAL_PAIRS = {
    "prerequisite_for": "depends_on",
    "depends_on": "prerequisite_for",
}
VALID_RELATION_TYPES = set(RELATION_TO_CYPHER.keys())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node_to_dict(node: Any) -> dict:
    """把 Neo4j Node 转成与旧 API 兼容的字典"""
    props = dict(node)
    return {
        "id": str(props.get("id", "")),
        "name": props.get("name", ""),
        "subject": props.get("subject", ""),
        "description": props.get("description", ""),
        "grade_level": props.get("grade_level"),
        "difficulty": props.get("difficulty", 1),
        "is_key_point": bool(props.get("is_key_point", False)),
        "owner_id": str(props.get("owner_id", "")),
        "created_at": props.get("created_at"),
    }


def _exam_to_dict(node: Any) -> dict:
    """Neo4j ExamPoint 节点转字典（考点：考纲要求 了解/理解/掌握）"""
    props = dict(node)
    return {
        "id": str(props.get("id", "")),
        "name": props.get("name", ""),
        "level": props.get("level", "理解"),
        "description": props.get("description", ""),
    }


def _mis_to_dict(node: Any) -> dict:
    """Neo4j Misconception 节点转字典（误区/易错点）"""
    props = dict(node)
    return {
        "id": str(props.get("id", "")),
        "content": props.get("content", ""),
        "correction": props.get("correction", ""),
    }


def _edge_to_dict(src_id: Any, dst_id: Any, rel_type: str) -> dict:
    """关系字典（显式投影，避免依赖 Relationship.start_node 的隐式绑定）"""
    return {
        "source_id": str(src_id),
        "target_id": str(dst_id),
        "relation_type": CYPHER_TO_RELATION.get(rel_type, rel_type.lower()),
    }


class KnowledgeGraphRepository:
    """知识图谱仓储：知识点/关系 CRUD、子图查询、全文搜索、批量写入"""

    def __init__(self) -> None:
        self._driver = get_neo4j_driver()

    def _run(self, query: str, **params: Any) -> list[Any]:
        """执行读查询，返回记录列表"""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            return list(session.run(query, **params))

    def _write(self, query: str, **params: Any) -> None:
        """执行写查询"""
        with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            session.run(query, **params)

    # ==================== 知识点 CRUD ====================

    def create_knowledge_point(
        self,
        *,
        owner_id: str,
        name: str,
        subject: str = "通用",
        description: str = "",
        grade_level: str | None = None,
        difficulty: int = 1,
        is_key_point: bool = False,
    ) -> dict:
        """创建知识点节点"""
        kp_id = str(uuid.uuid4())
        result = self._run(
            """
            CREATE (kp:KnowledgePoint {
                id: $id, name: $name, subject: $subject, description: $description,
                grade_level: $grade_level, difficulty: $difficulty,
                is_key_point: $is_key_point, owner_id: $owner_id, created_at: $created_at
            })
            RETURN kp
            """,
            id=kp_id,
            name=name,
            subject=subject,
            description=description,
            grade_level=grade_level,
            difficulty=difficulty,
            is_key_point=is_key_point,
            owner_id=owner_id,
            created_at=_now(),
        )
        return _node_to_dict(result[0]["kp"])

    def update_knowledge_point(self, kp_id: str, **fields: Any) -> dict | None:
        """更新知识点属性（仅更新传入的字段）"""
        allowed = {
            "name", "subject", "description", "grade_level",
            "difficulty", "is_key_point",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_knowledge_point(kp_id)
        set_clause = ", ".join(f"kp.{k} = ${k}" for k in updates)
        result = self._run(
            f"""
            MATCH (kp:KnowledgePoint {{id: $kp_id}})
            SET {set_clause}
            RETURN kp
            """,
            kp_id=kp_id,
            **updates,
        )
        if not result:
            return None
        return _node_to_dict(result[0]["kp"])

    def get_knowledge_point(self, kp_id: str) -> dict | None:
        """获取单个知识点"""
        result = self._run(
            "MATCH (kp:KnowledgePoint {id: $kp_id}) WHERE (kp.status IS NULL OR kp.status = 'published') RETURN kp",
            kp_id=kp_id,
        )
        return _node_to_dict(result[0]["kp"]) if result else None

    def get_many_knowledge_points(self, kp_ids: list[str]) -> list[dict]:
        """批量获取知识点（按 ID 列表，保持传入顺序中存在的节点）"""
        result = self._run(
            "MATCH (kp:KnowledgePoint) WHERE kp.id IN $ids AND (kp.status IS NULL OR kp.status = 'published') RETURN kp",
            ids=[i for i in kp_ids if i],
        )
        by_id = {str(r["kp"].get("id", "")): _node_to_dict(r["kp"]) for r in result}
        return [by_id[i] for i in kp_ids if i in by_id]

    def delete_knowledge_point(self, kp_id: str) -> bool:
        """删除知识点及其所有关系"""
        result = self._run(
            "MATCH (kp:KnowledgePoint {id: $kp_id}) WITH kp DETACH DELETE kp RETURN count(kp) AS n",
            kp_id=kp_id,
        )
        return result[0]["n"] > 0

    def list_knowledge_points(
        self,
        *,
        owner_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
        subject: str | None = None,
        grade_level: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        """列出知识点，支持按所有者/学科/学段/名称筛选"""
        where = ["(kp.status IS NULL OR kp.status = 'published')"]
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if owner_id is not None:
            where.append("kp.owner_id = $owner_id")
            params["owner_id"] = owner_id
        if subject:
            where.append("kp.subject = $subject")
            params["subject"] = subject
        if grade_level:
            where.append("kp.grade_level = $grade_level")
            params["grade_level"] = grade_level
        if search:
            where.append("toLower(kp.name) CONTAINS toLower($search)")
            params["search"] = search
        where_clause = " AND ".join(where)

        count_result = self._run(
            f"MATCH (kp:KnowledgePoint) WHERE {where_clause} RETURN count(kp) AS n",
            **{k: v for k, v in params.items() if k not in ("skip", "limit")},
        )
        result = self._run(
            f"""
            MATCH (kp:KnowledgePoint)
            WHERE {where_clause}
            RETURN kp
            ORDER BY kp.created_at DESC
            SKIP $skip LIMIT $limit
            """,
            **params,
        )
        return [_node_to_dict(r["kp"]) for r in result], count_result[0]["n"]

    def find_by_name(self, name: str, owner_id: str | None) -> dict | None:
        """按名称精确查找（提取/审核去重用）。

        owner_id=None 时全局查找——知识库为全局共享图谱，
        审核写图与批量导入必须全局按名去重，避免同名节点重复。
        """
        result = self._run(
            """
            MATCH (kp:KnowledgePoint {name: $name})
            WHERE $owner_id IS NULL OR kp.owner_id = $owner_id
            RETURN kp LIMIT 1
            """,
            name=name,
            owner_id=owner_id,
        )
        return _node_to_dict(result[0]["kp"]) if result else None

    # ==================== 关系 ====================

    def create_relation(
        self, source_id: str, target_id: str, relation_type: str
    ) -> dict | None:
        """创建知识点关系（幂等），返回边或 None（节点不存在时）。

        双向维护反向关系：prerequisite_for ⇄ depends_on 自动成对创建，
        parallel 自动创建反向边（无向语义），后续查询无需写反向逻辑。
        """
        if relation_type not in VALID_RELATION_TYPES:
            raise ValueError(f"非法关系类型: {relation_type}")
        if relation_type in ("has_exam_point", "has_misconception"):
            raise ValueError(f"{relation_type} 为知识点-实体关系，请使用专用 link 方法")
        rel = RELATION_TO_CYPHER[relation_type]
        result = self._run(
            f"""
            MATCH (a:KnowledgePoint {{id: $source_id}})
            MATCH (b:KnowledgePoint {{id: $target_id}})
            MERGE (a)-[r:{rel}]->(b)
            RETURN r, startNode(r) AS src, endNode(r) AS dst
            """,
            source_id=source_id,
            target_id=target_id,
        )
        if not result:
            return None

        # 双向维护
        reverse_type = BIDIRECTIONAL_PAIRS.get(relation_type)
        if reverse_type:
            reverse_rel = RELATION_TO_CYPHER[reverse_type]
            self._run(
                f"""
                MATCH (a:KnowledgePoint {{id: $source_id}})
                MATCH (b:KnowledgePoint {{id: $target_id}})
                MERGE (b)-[:{reverse_rel}]->(a)
                """,
                source_id=source_id,
                target_id=target_id,
            )
        elif relation_type == "parallel":
            # parallel 无向语义：自动建反向边
            self._run(
                f"""
                MATCH (a:KnowledgePoint {{id: $source_id}})
                MATCH (b:KnowledgePoint {{id: $target_id}})
                MERGE (b)-[:PARALLEL]->(a)
                """,
                source_id=source_id,
                target_id=target_id,
            )

        rec = result[0]
        return {
            "source_id": str(rec["src"]["id"]),
            "target_id": str(rec["dst"]["id"]),
            "relation_type": relation_type,
        }

    def delete_relation(
        self, source_id: str, target_id: str, relation_type: str | None = None
    ) -> bool:
        """删除关系；不指定类型时删除两节点间所有关系"""
        rel_filter = (
            f"[:{RELATION_TO_CYPHER[relation_type]}]"
            if relation_type in VALID_RELATION_TYPES
            else ""
        )
        result = self._run(
            f"""
            MATCH (a:KnowledgePoint {{id: $source_id}})-[r{rel_filter}]->(b:KnowledgePoint {{id: $target_id}})
            DELETE r RETURN count(r) AS n
            """,
            source_id=source_id,
            target_id=target_id,
        )
        return result[0]["n"] > 0

    def get_relations(self, kp_id: str) -> list[dict]:
        """获取某知识点的所有出入关系（带方向）"""
        result = self._run(
            """
            MATCH (a:KnowledgePoint)-[r]->(b:KnowledgePoint)
            WHERE a.id = $kp_id OR b.id = $kp_id
            RETURN r, a.id AS src, b.id AS dst
            """,
            kp_id=kp_id,
        )
        return [
            {
                "source_id": str(rec["src"]),
                "target_id": str(rec["dst"]),
                "relation_type": CYPHER_TO_RELATION.get(
                    rec["r"].type, rec["r"].type.lower()
                ),
            }
            for rec in result
        ]

    # ==================== 图查询 ====================

    def get_full_graph(self, owner_id: str | None = None) -> dict:
        """获取全图：所有知识点节点及其关系（纯 Cypher）"""
        params: dict[str, Any] = {}
        owner_filter = "1 = 1"
        if owner_id is not None:
            owner_filter = "kp.owner_id = $owner_id"
            params["owner_id"] = owner_id
        node_result = self._run(
            f"MATCH (kp:KnowledgePoint) WHERE {owner_filter} RETURN kp", **params
        )
        rel_result = self._run(
            f"""
            MATCH (a:KnowledgePoint)-[r]->(b:KnowledgePoint)
            WHERE {owner_filter.replace('kp', 'a')}
            RETURN r, a.id AS src, b.id AS dst
            """,
            **params,
        )
        return {
            "nodes": [_node_to_dict(r["kp"]) for r in node_result],
            "edges": [
                {
                    "source_id": str(rec["src"]),
                    "target_id": str(rec["dst"]),
                    "relation_type": CYPHER_TO_RELATION.get(
                        rec["r"].type, rec["r"].type.lower()
                    ),
                }
                for rec in rel_result
            ],
        }

    def get_subgraph(self, center_id: str, depth: int = 2) -> dict:
        """以某知识点为中心的子图（变长路径，纯 Cypher，无需 APOC）"""
        result = self._run(
            """
            MATCH (center:KnowledgePoint {id: $center_id})
            OPTIONAL MATCH path = (center)-[*1..$depth]-(n:KnowledgePoint)
            WITH center, n, path
            UNWIND relationships(path) AS r
            RETURN collect(DISTINCT n) AS nodes,
                   collect(DISTINCT {source_id: startNode(r).id, target_id: endNode(r).id, type: type(r)}) AS edges
            """,
            center_id=center_id,
            depth=max(1, depth),
        )
        if not result:
            return {"nodes": [], "edges": []}
        record = result[0]
        nodes = [_node_to_dict(n) for n in (record["nodes"] or [])]
        center = self.get_knowledge_point(center_id)
        if center and center not in nodes:
            nodes.append(center)
        edges = [
            {
                "source_id": str(e["source_id"]),
                "target_id": str(e["target_id"]),
                "relation_type": CYPHER_TO_RELATION.get(
                    e["type"], e["type"].lower()
                ),
            }
            for e in (record["edges"] or [])
        ]
        return {"nodes": nodes, "edges": edges}

    def search_knowledge_points(self, query: str, owner_id: str | None, top_k: int = 10) -> list[dict]:
        """分词打分检索（名称命中权重高于描述命中），供 Agent 工具与兜底检索复用。

        强制过滤 status：只返回已发布（published）的知识点，
        未审核数据不会进入任何备课查询。兼容存量节点（无 status 视为已发布）。
        """
        tokens = [
            t.strip()
            for t in re.split(r"[\s,，。、;；:：!！?？()（）【】\[\]\"']+", query)
            if len(t.strip()) >= 2
        ][:8]
        if not tokens:
            return []
        result = self._run(
            """
            MATCH (kp:KnowledgePoint)
            WHERE ($owner_id IS NULL OR kp.owner_id = $owner_id)
              AND (kp.status IS NULL OR kp.status = 'published')
            WITH kp,
                 reduce(s = 0, t IN $tokens |
                   s + CASE
                     WHEN toLower(kp.name) CONTAINS toLower(t) THEN 3
                     WHEN toLower(kp.description) CONTAINS toLower(t) THEN 1
                     ELSE 0 END) AS score
            WHERE score > 0
            RETURN kp, score
            ORDER BY score DESC, kp.created_at DESC
            LIMIT $top_k
            """,
            tokens=tokens,
            owner_id=owner_id,
            top_k=top_k,
        )
        return [_node_to_dict(r["kp"]) for r in result]

    def count_key_points(self, subject: str | None = None) -> int:
        """统计全局核心知识点（is_key_point=true，published）数量，完整度评分分母"""
        if subject:
            result = self._run(
                """
                MATCH (kp:KnowledgePoint)
                WHERE kp.is_key_point = true AND kp.subject = $subject
                  AND (kp.status IS NULL OR kp.status = 'published')
                RETURN count(kp) AS n
                """,
                subject=subject,
            )
        else:
            result = self._run(
                """
                MATCH (kp:KnowledgePoint)
                WHERE kp.is_key_point = true
                  AND (kp.status IS NULL OR kp.status = 'published')
                RETURN count(kp) AS n
                """
            )
        return int(result[0]["n"]) if result else 0

    def count_knowledge_points(self, owner_id: str | None) -> int:
        """统计知识点数量（强制触发兜底的校验规则用）"""
        params: dict[str, Any] = {"owner_id": owner_id}
        owner_filter = "kp.owner_id = $owner_id" if owner_id is not None else "1 = 1"
        result = self._run(
            f"MATCH (kp:KnowledgePoint) WHERE {owner_filter} RETURN count(kp) AS n",
            **params,
        )
        return result[0]["n"]

    def list_knowledge_point_names(self, owner_id: str | None, limit: int = 500) -> list[str]:
        """列出知识点名称（供查询词提取时做已有名称匹配）"""
        params: dict[str, Any] = {"limit": limit}
        owner_filter = "1 = 1"
        if owner_id is not None:
            owner_filter = "kp.owner_id = $owner_id"
            params["owner_id"] = owner_id
        result = self._run(
            f"""
            MATCH (kp:KnowledgePoint) WHERE {owner_filter}
            RETURN kp.name AS name LIMIT $limit
            """,
            **params,
        )
        return [r["name"] for r in result]

    def get_neighbors(self, kp_id: str, depth: int = 1) -> list[dict]:
        """获取某知识点的邻居（供 Agent 图谱遍历工具使用）。

        注意：Cypher 可变长度模式的上界不能参数化（`*1..$depth` 是非法语法），
        depth 先 clamp 到 1-2 再内联进查询。
        """
        depth = min(max(depth, 1), 2)
        rel_types = "|".join(KP_TO_KP_REL_TYPES)
        result = self._run(
            f"""
            MATCH (kp:KnowledgePoint {{id: $kp_id}})-[:{rel_types}*1..{depth}]-(n:KnowledgePoint)
            WHERE (n.status IS NULL OR n.status = 'published')
            RETURN DISTINCT n
            LIMIT 50
            """,
            kp_id=kp_id,
        )
        return [_node_to_dict(r["n"]) for r in result]

    def get_prerequisites(self, kp_id: str) -> list[dict]:
        """获取某知识点的直接前置知识点（Agent 备课工具用）"""
        result = self._run(
            """
            MATCH (kp:KnowledgePoint {id: $kp_id})-[:PREREQUISITE]->(pre)
            WHERE (pre.status IS NULL OR pre.status = 'published')
            RETURN pre
            """,
            kp_id=kp_id,
        )
        return [_node_to_dict(r["pre"]) for r in result]

    def graph_quality_check(self) -> dict:
        """图谱质量检测（管理员后台告警数据源）。

        检测三类问题：
        1. 循环依赖：A→B 且 B→A（PREREQUISITE/DEPENDS_ON/CONTAINS 方向）
        2. 孤立节点：无任何关系的知识点
        3. 核心知识点缺少前置：is_key_point=true 且无任何前置/依赖边
        """
        # 仅检测「真正非法」的环：PREREQUISITE/CONTAINS 同型自环
        # （parallel 双向边、prerequisite_for⇄depends_on 成对边是设计行为，不报警）
        cycles = self._run(
            """
            MATCH (a:KnowledgePoint)-[r1]->(b:KnowledgePoint)-[r2]->(a)
            WHERE type(r1) = type(r2)
              AND type(r1) IN ['PREREQUISITE', 'CONTAINS']
              AND a.id < b.id
            RETURN a.name AS name_a, b.name AS name_b, type(r1) AS rel1
            LIMIT 50
            """
        )
        isolated = self._run(
            """
            MATCH (kp:KnowledgePoint)
            WHERE NOT (kp)--()
            RETURN kp.name AS name
            LIMIT 50
            """
        )
        key_missing_pre = self._run(
            """
            MATCH (kp:KnowledgePoint)
            WHERE kp.is_key_point = true
              AND NOT (kp)-[:PREREQUISITE|DEPENDS_ON]->(:KnowledgePoint)
              AND NOT (:KnowledgePoint)-[:PREREQUISITE|DEPENDS_ON]->(kp)
            RETURN kp.name AS name
            LIMIT 50
            """
        )
        return {
            "cycles": [dict(r) for r in cycles],
            "isolated_nodes": [r["name"] for r in isolated],
            "key_points_without_dependencies": [r["name"] for r in key_missing_pre],
        }

    def get_prerequisite_chain(self, kp_id: str, max_depth: int = 3) -> list[dict]:
        """递归查询前置依赖链（备课参考面板「前置预备知识」数据源）。

        沿 PREREQUISITE/DEPENDS_ON 方向展开至 max_depth 层，
        按深度升序返回去重后的前置知识点（一层=直接前置）。
        """
        result = self._run(
            f"""
            MATCH path = (kp:KnowledgePoint {{id: $kp_id}})-[:PREREQUISITE|DEPENDS_ON*1..{max_depth}]->(pre:KnowledgePoint)
            WHERE (pre.status IS NULL OR pre.status = 'published')
            RETURN pre, length(path) AS depth
            ORDER BY depth
            """,
            kp_id=kp_id,
        )
        seen: set[str] = set()
        chain: list[dict] = []
        for r in result:
            kp = _node_to_dict(r["pre"])
            if kp["id"] not in seen:
                seen.add(kp["id"])
                chain.append({**kp, "depth": int(r["depth"])})
        return chain

    # ==================== 考点实体（ExamPoint） ====================

    def create_exam_point(
        self,
        *,
        owner_id: str,
        name: str,
        level: str = "理解",  # 了解 / 理解 / 掌握
        description: str = "",
    ) -> dict:
        """创建考点实体（对应考纲要求，挂在知识点下）"""
        exam_id = str(uuid.uuid4())
        result = self._run(
            """
            CREATE (e:ExamPoint {
                id: $id, name: $name, level: $level, description: $description,
                owner_id: $owner_id, created_at: $created_at
            })
            RETURN e
            """,
            id=exam_id,
            name=name,
            level=level,
            description=description,
            owner_id=owner_id,
            created_at=_now(),
        )
        return _exam_to_dict(result[0]["e"])

    def link_kp_exam_point(self, kp_id: str, exam_point_id: str) -> dict | None:
        """知识点 -[:HAS_EXAM_POINT]-> 考点"""
        result = self._run(
            """
            MATCH (kp:KnowledgePoint {id: $kp_id})
            MATCH (e:ExamPoint {id: $exam_id})
            MERGE (kp)-[:HAS_EXAM_POINT]->(e)
            RETURN e
            """,
            kp_id=kp_id,
            exam_id=exam_point_id,
        )
        return _exam_to_dict(result[0]["e"]) if result else None

    def get_exam_points(self, kp_id: str) -> list[dict]:
        """获取知识点关联的考点列表"""
        result = self._run(
            """
            MATCH (kp:KnowledgePoint {id: $kp_id})-[:HAS_EXAM_POINT]->(e:ExamPoint)
            RETURN e ORDER BY e.level
            """,
            kp_id=kp_id,
        )
        return [_exam_to_dict(r["e"]) for r in result]

    def delete_exam_point(self, exam_point_id: str) -> bool:
        result = self._run(
            "MATCH (e:ExamPoint {id: $id}) WITH e DETACH DELETE e RETURN count(e) AS n",
            id=exam_point_id,
        )
        return result[0]["n"] > 0

    # ==================== 误区实体（Misconception） ====================

    def create_misconception(
        self,
        *,
        owner_id: str,
        content: str,
        correction: str = "",
    ) -> dict:
        """创建误区实体（学生常见错误概念 / 易错点）"""
        mis_id = str(uuid.uuid4())
        result = self._run(
            """
            CREATE (m:Misconception {
                id: $id, content: $content, correction: $correction,
                owner_id: $owner_id, created_at: $created_at
            })
            RETURN m
            """,
            id=mis_id,
            content=content,
            correction=correction,
            owner_id=owner_id,
            created_at=_now(),
        )
        return _mis_to_dict(result[0]["m"])

    def link_kp_misconception(self, kp_id: str, misconception_id: str) -> dict | None:
        """知识点 -[:HAS_MISCONCEPTION]-> 误区"""
        result = self._run(
            """
            MATCH (kp:KnowledgePoint {id: $kp_id})
            MATCH (m:Misconception {id: $mis_id})
            MERGE (kp)-[:HAS_MISCONCEPTION]->(m)
            RETURN m
            """,
            kp_id=kp_id,
            mis_id=misconception_id,
        )
        return _mis_to_dict(result[0]["m"]) if result else None

    def get_misconceptions(self, kp_id: str) -> list[dict]:
        """获取知识点关联的误区列表"""
        result = self._run(
            """
            MATCH (kp:KnowledgePoint {id: $kp_id})-[:HAS_MISCONCEPTION]->(m:Misconception)
            RETURN m
            """,
            kp_id=kp_id,
        )
        return [_mis_to_dict(r["m"]) for r in result]

    def delete_misconception(self, misconception_id: str) -> bool:
        result = self._run(
            "MATCH (m:Misconception {id: $id}) WITH m DETACH DELETE m RETURN count(m) AS n",
            id=misconception_id,
        )
        return result[0]["n"] > 0

    # ==================== 批量写入（提取图用） ====================

    def merge_knowledge_points(self, owner_id: str, kps: list[dict]) -> list[str]:
        """批量按名称去重创建知识点，返回 [kp_id]（与输入顺序对应，已存在则复用）"""
        kp_ids = self.find_or_create_batch(owner_id, kps)
        return kp_ids

    def find_or_create_batch(self, owner_id: str, kps: list[dict]) -> list[str]:
        """逐条 find_by_name + create（正确性优先，数据量不大时可接受）"""
        ids: list[str] = []
        for kp in kps:
            name = (kp.get("name") or "").strip()
            if not name:
                ids.append("")
                continue
            existing = self.find_by_name(name, owner_id)
            if existing:
                # 新描述更详细时补全
                desc = kp.get("description") or ""
                if desc and (not existing["description"] or len(desc) > len(existing["description"])):
                    self.update_knowledge_point(existing["id"], description=desc)
                ids.append(existing["id"])
            else:
                created = self.create_knowledge_point(
                    owner_id=owner_id,
                    name=name,
                    subject=kp.get("subject") or "通用",
                    description=(kp.get("description") or "")[:2000],
                    difficulty=int(kp.get("difficulty", 1)),
                    is_key_point=bool(kp.get("is_key_point", False)),
                )
                ids.append(created["id"])
        return ids

    def merge_relations(self, owner_id: str, relations: list[dict]) -> int:
        """批量创建关系（源/目标不存在时静默跳过），返回成功数"""
        created = 0
        for rel in relations:
            source_id = rel.get("source_id")
            target_id = rel.get("target_id")
            rel_type = rel.get("relation_type", "related_to")
            if not source_id or not target_id or rel_type not in VALID_RELATION_TYPES:
                continue
            try:
                if self.create_relation(str(source_id), str(target_id), rel_type):
                    created += 1
            except Exception:
                continue
        return created

    def link_document_knowledge_points(self, document_id: str, kp_ids: list[str]) -> None:
        """建立 文档-知识点 MENTIONS 关系，同时维护文档元数据节点"""
        self._run(
            """
            MERGE (d:Document {id: $document_id})
            RETURN d
            """,
            document_id=document_id,
        )
        for kp_id in kp_ids:
            self._run(
                """
                MATCH (d:Document {id: $document_id})
                MATCH (kp:KnowledgePoint {id: $kp_id})
                MERGE (d)-[:MENTIONS]->(kp)
                """,
                document_id=document_id,
                kp_id=kp_id,
            )

    def get_document_knowledge_points(self, document_id: str) -> list[dict]:
        """获取文档关联的知识点"""
        result = self._run(
            """
            MATCH (d:Document {id: $document_id})-[:MENTIONS]->(kp:KnowledgePoint)
            RETURN kp
            """,
            document_id=document_id,
        )
        return [_node_to_dict(r["kp"]) for r in result]

    def link_lesson_plan_knowledge_points(self, lesson_plan_id: str, kp_ids: list[str]) -> None:
        """建立 教案-知识点 COVERS 关系"""
        self._run(
            """
            MERGE (lp:LessonPlan {id: $lesson_plan_id})
            RETURN lp
            """,
            lesson_plan_id=lesson_plan_id,
        )
        for kp_id in kp_ids:
            self._run(
                """
                MATCH (lp:LessonPlan {id: $lesson_plan_id})
                MATCH (kp:KnowledgePoint {id: $kp_id})
                MERGE (lp)-[:COVERS]->(kp)
                """,
                lesson_plan_id=lesson_plan_id,
                kp_id=kp_id,
            )

    def get_lesson_plan_knowledge_points(self, lesson_plan_id: str) -> list[dict]:
        """获取教案覆盖的知识点"""
        result = self._run(
            """
            MATCH (lp:LessonPlan {id: $lesson_plan_id})-[:COVERS]->(kp:KnowledgePoint)
            RETURN kp
            """,
            lesson_plan_id=lesson_plan_id,
        )
        return [_node_to_dict(r["kp"]) for r in result]


# 全局单例仓储
_repository: Optional[KnowledgeGraphRepository] = None


def get_knowledge_graph() -> KnowledgeGraphRepository:
    """获取知识图谱仓储单例"""
    global _repository
    if _repository is None:
        _repository = KnowledgeGraphRepository()
    return _repository
