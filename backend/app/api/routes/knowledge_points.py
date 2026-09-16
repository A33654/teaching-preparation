"""知识点 API —— 数据源为 Neo4j 知识图谱（app/knowledge_graph/）。"""
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.knowledge_graph import KnowledgeGraphRepository
from app.models import (
    KnowledgePointCreate,
    KnowledgePointOut,
    KnowledgePointsPublic,
    KnowledgePointUpdate,
    KnowledgeRelationCreate,
    KnowledgeRelationOut,
)


class SubgraphEdge(BaseModel):
    source_id: str
    target_id: str
    relation_type: str


class SubgraphResponse(BaseModel):
    nodes: list[dict]
    edges: list[SubgraphEdge]


router = APIRouter(prefix="/knowledge-points", tags=["knowledge-points"])


def _repo() -> KnowledgeGraphRepository:
    return KnowledgeGraphRepository()


def _check_access(
    repo: KnowledgeGraphRepository,
    kp_id: str,
    current_user: Any,
) -> dict:
    """权限校验：存在且是本人的知识点（超级管理员放行）"""
    kp = repo.get_knowledge_point(kp_id)
    if not kp:
        raise HTTPException(status_code=404, detail="知识点不存在")
    if not current_user.is_superuser and kp.get("owner_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问")
    return kp


# ==================== 全图查询 ====================


@router.get("/graph/full", response_model=SubgraphResponse)
def get_full_graph(session: SessionDep, current_user: CurrentUser) -> Any:
    """获取当前用户所有知识点及其关系的全图（Neo4j）"""
    repo = _repo()
    owner_id = None if current_user.is_superuser else str(current_user.id)
    graph = repo.get_full_graph(owner_id)
    return SubgraphResponse(
        nodes=graph["nodes"],
        edges=[SubgraphEdge(**e) for e in graph["edges"]],
    )


# ==================== 知识点 CRUD ====================


@router.get("/", response_model=KnowledgePointsPublic)
def read_knowledge_points(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    subject: str | None = Query(default=None, description="按学科筛选"),
    grade_level: str | None = Query(default=None, description="按学段筛选"),
    search: str | None = Query(default=None, description="按名称搜索"),
) -> Any:
    """获取知识点列表（Neo4j），支持按学科、学段筛选和名称搜索"""
    repo = _repo()
    owner_id = None if current_user.is_superuser else str(current_user.id)
    items, count = repo.list_knowledge_points(
        owner_id=owner_id,
        skip=skip,
        limit=limit,
        subject=subject,
        grade_level=grade_level,
        search=search,
    )
    return KnowledgePointsPublic(
        data=[KnowledgePointOut(**kp) for kp in items],
        count=count,
    )


@router.get("/{id}", response_model=KnowledgePointOut)
def read_knowledge_point(
    id: str, session: SessionDep, current_user: CurrentUser
) -> Any:
    """获取单个知识点详情"""
    kp = _check_access(_repo(), id, current_user)
    return KnowledgePointOut(**kp)


@router.post("/", response_model=KnowledgePointOut)
def create_knowledge_point(
    *, session: SessionDep, current_user: CurrentUser, kp_in: KnowledgePointCreate
) -> Any:
    """创建新知识点（写入 Neo4j）"""
    repo = _repo()
    kp = repo.create_knowledge_point(
        owner_id=str(current_user.id),
        name=kp_in.name,
        subject=kp_in.subject,
        description=kp_in.description or "",
        grade_level=kp_in.grade_level.value if kp_in.grade_level else None,
        difficulty=kp_in.difficulty,
        is_key_point=kp_in.is_key_point,
    )
    return KnowledgePointOut(**kp)


@router.put("/{id}", response_model=KnowledgePointOut)
def update_knowledge_point(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: str,
    kp_in: KnowledgePointUpdate,
) -> Any:
    """更新知识点（Neo4j 节点属性）"""
    repo = _repo()
    _check_access(repo, id, current_user)
    fields = kp_in.model_dump(exclude_unset=True)
    if "grade_level" in fields and fields["grade_level"] is not None:
        fields["grade_level"] = fields["grade_level"].value
    updated = repo.update_knowledge_point(id, **fields)
    if not updated:
        raise HTTPException(status_code=404, detail="知识点不存在")
    return KnowledgePointOut(**updated)


@router.delete("/{id}")
def delete_knowledge_point(
    id: str, session: SessionDep, current_user: CurrentUser
) -> dict:
    """删除知识点（Neo4j DETACH DELETE，级联删除关系）"""
    repo = _repo()
    _check_access(repo, id, current_user)
    repo.delete_knowledge_point(id)
    return {"message": "知识点已删除"}


# ==================== 知识点关系 ====================


@router.post("/{id}/relations", response_model=KnowledgeRelationOut)
def create_knowledge_relation(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: str,
    relation_in: KnowledgeRelationCreate,
) -> Any:
    """为知识点创建关系（Neo4j 边）"""
    repo = _repo()
    _check_access(repo, id, current_user)
    target = repo.get_knowledge_point(relation_in.target_id)
    if not target:
        raise HTTPException(status_code=404, detail="目标知识点不存在")
    if not current_user.is_superuser and target.get("owner_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权操作目标知识点")
    edge = repo.create_relation(id, relation_in.target_id, relation_in.relation_type)
    if not edge:
        raise HTTPException(status_code=400, detail="创建关系失败")
    return KnowledgeRelationOut(**edge)


@router.get("/{id}/relations", response_model=list[KnowledgeRelationOut])
def read_knowledge_relations(
    id: str, session: SessionDep, current_user: CurrentUser
) -> Any:
    """获取某知识点的所有关系（出边和入边）"""
    _check_access(_repo(), id, current_user)
    return [KnowledgeRelationOut(**e) for e in _repo().get_relations(id)]


@router.delete("/{id}/relations")
def delete_knowledge_relation(
    id: str,
    session: SessionDep,
    current_user: CurrentUser,
    target_id: str,
    relation_type: str = "related_to",
) -> dict:
    """删除知识点关系"""
    repo = _repo()
    _check_access(repo, id, current_user)
    ok = repo.delete_relation(id, target_id, relation_type)
    if not ok:
        raise HTTPException(status_code=404, detail="关系不存在")
    return {"message": "关系已删除"}


# ==================== 子图查询 ====================


@router.get("/{id}/subgraph", response_model=SubgraphResponse)
def get_knowledge_subgraph(
    id: str,
    session: SessionDep,
    current_user: CurrentUser,
    depth: int = 2,
) -> Any:
    """获取以某知识点为中心的子图（Neo4j 变长路径遍历）"""
    repo = _repo()
    _check_access(repo, id, current_user)
    graph = repo.get_subgraph(id, depth=depth)
    return SubgraphResponse(
        nodes=graph["nodes"],
        edges=[SubgraphEdge(**e) for e in graph["edges"]],
    )


# ==================== 知识搜索 ====================


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


@router.post("/search")
def search_knowledge(
    body: SearchRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """用自然语言关键词搜索知识图谱节点（Neo4j）"""
    repo = _repo()
    owner_id = None if current_user.is_superuser else str(current_user.id)
    results = repo.search_knowledge_points(body.query, owner_id, top_k=body.top_k)
    return {"query": body.query, "results": results}


class ChapterContextRequest(BaseModel):
    chapter: str
    subject: str = ""


@router.post("/chapter-context")
def chapter_context(
    body: ChapterContextRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """章节自动联动：检索本章知识点及前置依赖，判断知识库完整度。

    统一备课工作台右侧预览区数据源——教师只选章节，
    系统自动加载本章图谱结构（知识点清单 + 前置依赖 + 完整度判断）。
    """
    repo = _repo()
    # 知识库为全局共享图谱（管理员审核维护），备课联动不过滤 owner
    hits = repo.search_knowledge_points(body.chapter, None, top_k=20)

    # 每个命中的知识点补充前置依赖 + 考点 + 误区信息
    enriched = []
    for kp in hits:
        prereqs: list[str] = []
        exam_points: list[dict] = []
        misconceptions: list[dict] = []
        try:
            rels = repo.get_prerequisites(kp["id"])
            prereqs = [r["name"] for r in rels]
        except Exception:
            pass
        try:
            exam_points = repo.get_exam_points(kp["id"])
        except Exception:
            pass
        try:
            misconceptions = repo.get_misconceptions(kp["id"])
        except Exception:
            pass
        enriched.append(
            {
                **kp,
                "prerequisites": prereqs,
                "exam_points": exam_points,
                "misconceptions": misconceptions,
            }
        )

    # 知识库完整度评分：命中核心知识点占比（区别于简单数量统计）
    key_hit = sum(1 for k in hits if k.get("is_key_point"))
    key_total = repo.count_key_points(body.subject or None)
    if not hits:
        coverage = "missing"
        message = "知识库尚未收录本章节，将自动 RAG 兜底增强"
    elif key_total > 0 and key_hit / key_total >= 0.8:
        coverage = "complete"
        message = f"知识库完整（核心知识点覆盖 {key_hit}/{key_total}），将基于图谱 + 教材精准生成教案"
    else:
        coverage = "partial"
        message = (
            f"知识库部分缺失（核心知识点覆盖 {key_hit}/{key_total}），将自动 RAG 兜底增强"
            if key_total > 0
            else "知识库部分缺失，将自动 RAG 兜底增强"
        )

    # ==================== 图谱计算的业务清单 ====================

    # ① 教学顺序建议：按前置依赖拓扑排序（无前置的在前）
    kp_names = {k["name"] for k in hits}
    order: list[str] = []
    remaining = list(hits)
    while remaining:
        # 找前置都已入序（或不在本章）的知识点
        ready = [
            k for k in remaining
            if all(
                (p in order) or (p not in kp_names)
                for p in (k.get("prerequisites") or [])
            )
        ]
        if not ready:  # 环保护：剩余全部追加
            order.extend(k["name"] for k in remaining)
            break
        for k in ready:
            order.append(k["name"])
            remaining.remove(k)
    # 不在排序内的补充（理论上不会发生）
    for k in hits:
        if k["name"] not in order:
            order.append(k["name"])

    # ② 本节重难点：difficulty>=4 或核心考点 → 重点；difficulty>=3 → 难点
    key_difficult = []
    for k in hits:
        diff = k.get("difficulty") or 1
        reasons = []
        if k.get("is_key_point"):
            reasons.append("核心考点")
        if diff >= 4:
            reasons.append(f"难度 {diff}/5")
        if reasons:
            key_difficult.append({"name": k["name"], "reasons": reasons})

    # ③ 前置预备知识：递归依赖链（取所有命中知识点的并集，按深度排序）
    chain_map: dict[str, dict] = {}
    for kp in hits:
        try:
            for pre in repo.get_prerequisite_chain(kp["id"], max_depth=3):
                if pre["name"] not in chain_map or chain_map[pre["name"]]["depth"] > pre["depth"]:
                    chain_map[pre["name"]] = pre
        except Exception:
            pass
    prereq_chain = sorted(chain_map.values(), key=lambda x: x["depth"])

    return {
        "chapter": body.chapter,
        "knowledge_points": enriched,
        "coverage": coverage,
        "message": message,
        "teaching_order": order,
        "key_difficult_points": key_difficult,
        "prerequisite_chain": prereq_chain,
    }


# ==================== 考点 / 误区实体管理 ====================


class ExamPointCreate(BaseModel):
    name: str
    level: str = "理解"  # 了解 / 理解 / 掌握
    description: str = ""


class MisconceptionCreate(BaseModel):
    content: str
    correction: str = ""


@router.get("/{id}/exam-points")
def read_exam_points(
    id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """获取知识点关联的考点列表（考纲要求：了解/理解/掌握）"""
    repo = _repo()
    return {"data": repo.get_exam_points(id)}


@router.post("/{id}/exam-points")
def create_exam_point(
    id: str,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: ExamPointCreate,
) -> Any:
    """为知识点添加考点（知识点 -[:HAS_EXAM_POINT]-> 考点）"""
    repo = _repo()
    exam = repo.create_exam_point(
        owner_id=str(current_user.id),
        name=body.name,
        level=body.level,
        description=body.description,
    )
    repo.link_kp_exam_point(id, exam["id"])
    return exam


@router.delete("/{id}/exam-points/{exam_id}")
def delete_exam_point(
    id: str,
    exam_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    repo = _repo()
    repo.delete_exam_point(exam_id)
    return {"message": "考点已删除"}


@router.get("/{id}/misconceptions")
def read_misconceptions(
    id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """获取知识点关联的误区列表（学生常见错误概念）"""
    repo = _repo()
    return {"data": repo.get_misconceptions(id)}


@router.post("/{id}/misconceptions")
def create_misconception(
    id: str,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: MisconceptionCreate,
) -> Any:
    """为知识点添加误区（知识点 -[:HAS_MISCONCEPTION]-> 误区）"""
    repo = _repo()
    mis = repo.create_misconception(
        owner_id=str(current_user.id),
        content=body.content,
        correction=body.correction,
    )
    repo.link_kp_misconception(id, mis["id"])
    return mis


@router.delete("/{id}/misconceptions/{mis_id}")
def delete_misconception(
    id: str,
    mis_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    repo = _repo()
    repo.delete_misconception(mis_id)
    return {"message": "误区已删除"}
