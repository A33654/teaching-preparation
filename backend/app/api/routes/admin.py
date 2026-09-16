"""管理员后台 API：待审核知识点队列、统计看板、系统任务日志。

审核流：LLM 抽取 / 教师提交 → 候选队列（pending）→ 管理员通过 → 写入 Neo4j 图谱。
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.knowledge_graph import KnowledgeGraphRepository
from app.models import (
    AdminStats,
    CandidateCreate,
    CandidateKnowledgePoint,
    CandidatePublic,
    CandidateUpdate,
    CandidatesPublic,
    Document,
    DocumentStatus,
    ExtractionLog,
    ExtractionLogPublic,
    ExtractionLogsPublic,
    KnowledgeSuggestion,
    Subject,
    SuggestionCreate,
    SuggestionPublic,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _log(session: Session, task_type: str, status: str, message: str) -> None:
    """写系统任务日志"""
    session.add(ExtractionLog(task_type=task_type, status=status, message=message[:2000]))
    session.commit()


# ==================== 统计看板 ====================


@router.get("/stats", response_model=AdminStats)
def admin_stats(
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """管理员工作台统计卡片数据"""
    pending = session.exec(
        select(func.count())
        .select_from(CandidateKnowledgePoint)
        .where(CandidateKnowledgePoint.status == "pending")
    ).one()
    subjects = session.exec(select(func.count()).select_from(Subject)).one()
    docs_total = session.exec(select(func.count()).select_from(Document)).one()
    docs_processing = session.exec(
        select(func.count())
        .select_from(Document)
        .where(
            Document.status.in_(
                [DocumentStatus.UPLOADED, DocumentStatus.PARSING, DocumentStatus.ANALYZING]
            )
        )
    ).one()
    docs_failed = session.exec(
        select(func.count())
        .select_from(Document)
        .where(Document.status == DocumentStatus.FAILED)
    ).one()
    repo = KnowledgeGraphRepository()
    kp_count = repo.count_knowledge_points(None)
    return AdminStats(
        pending_candidates=pending,
        subjects_count=subjects,
        knowledge_points_count=kp_count,
        documents_total=docs_total,
        documents_processing=docs_processing,
        documents_failed=docs_failed,
    )


# ==================== 待审核知识点队列 ====================


@router.get("/candidates", response_model=CandidatesPublic)
def list_candidates(
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
    status: str = "",
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """候选知识点列表（status: pending | approved | rejected，空 = 全部）"""
    where = []
    if status:
        where.append(CandidateKnowledgePoint.status == status)
    count = session.exec(
        select(func.count())
        .select_from(CandidateKnowledgePoint)
        .where(*where)
    ).one()
    statement = (
        select(CandidateKnowledgePoint)
        .where(*where)
        .order_by(col(CandidateKnowledgePoint.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    rows = session.exec(statement).all()
    return CandidatesPublic(
        data=[CandidatePublic.model_validate(r, from_attributes=True) for r in rows],
        count=count,
    )


@router.post("/candidates", response_model=CandidatePublic)
def submit_candidate(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: CandidateCreate,
) -> Any:
    """教师端提交候选知识点（手动补充缺失知识点）"""
    cand = CandidateKnowledgePoint(
        name=body.name,
        subject=body.subject,
        grade_level=body.grade_level,
        textbook_version=body.textbook_version,
        definition=body.definition,
        prerequisites=body.prerequisites,
        source="teacher_submit",
        status="pending",
        submitter_id=current_user.id,
        kind=body.kind,
        target_kp_id=body.target_kp_id,
        suggestion=body.suggestion,
    )
    session.add(cand)
    session.commit()
    session.refresh(cand)
    _log(
        session,
        "candidate_submit",
        "info",
        f"教师提交候选知识点「{cand.name}」",
    )
    return CandidatePublic.model_validate(cand, from_attributes=True)


@router.patch("/candidates/{id}", response_model=CandidatePublic)
def edit_candidate(
    id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
    body: CandidateUpdate,
) -> Any:
    """管理员编辑候选知识点"""
    cand = session.get(CandidateKnowledgePoint, id)
    if not cand:
        raise HTTPException(status_code=404, detail="候选知识点不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(cand, field, value)
    session.add(cand)
    session.commit()
    session.refresh(cand)
    return CandidatePublic.model_validate(cand, from_attributes=True)


def _normalize_kind(kind: str | None) -> str:
    """归一化工单类型：兼容候选表 teacher_* 前缀与建议表裸 kind"""
    k = kind or "llm_extraction"
    if k.startswith("teacher_"):
        k = k[len("teacher_"):]
    return k


def _approve_candidate(session: Session, cand: CandidateKnowledgePoint) -> str:
    """按工单类型分发审核通过动作，返回处理摘要。

    教师提交的全部是建议工单，审核通过后才真正写入图谱：
    - missing_kp / llm_extraction / auto_optimization → 按名全局查重创建/更新知识点
    - correction → 用审核后的 definition 更新目标知识点
    - misconception → 在目标知识点下创建误区实体（name=误区内容, suggestion=纠正）
    - exam_point → 在目标知识点下创建考点（name=考点名, suggestion=层次, definition=描述）
    """
    repo = KnowledgeGraphRepository()
    owner_id = str(cand.submitter_id)
    kind = _normalize_kind(cand.kind)

    if kind == "correction":
        if not cand.target_kp_id:
            raise ValueError("纠错工单缺少目标知识点")
        kp = repo.get_knowledge_point(cand.target_kp_id)
        if not kp:
            raise ValueError("目标知识点不存在")
        repo.update_knowledge_point(
            cand.target_kp_id,
            description=(cand.definition or cand.suggestion or kp["description"] or ""),
            subject=cand.subject or kp["subject"],
            grade_level=cand.grade_level,
        )
        return f"纠错已应用到「{kp['name']}」"

    if kind == "misconception":
        if not cand.target_kp_id:
            raise ValueError("误区工单缺少目标知识点")
        mis = repo.create_misconception(
            owner_id=owner_id,
            content=cand.name,
            correction=cand.suggestion or "",
        )
        repo.link_kp_misconception(cand.target_kp_id, mis["id"])
        return f"误区已关联到知识点 {cand.target_kp_id[:8]}"

    if kind == "exam_point":
        if not cand.target_kp_id:
            raise ValueError("考点工单缺少目标知识点")
        exam = repo.create_exam_point(
            owner_id=owner_id,
            name=cand.name,
            level=(cand.suggestion or "理解"),
            description=cand.definition or "",
        )
        repo.link_kp_exam_point(cand.target_kp_id, exam["id"])
        return f"考点「{cand.name}（{cand.suggestion or '理解'}）」已关联"

    # 默认：创建/更新知识点（llm_extraction / teacher_missing_kp / auto_optimization）
    existing = repo.find_by_name(cand.name, None)  # 全局查重
    if existing:
        kp_id = existing["id"]
        repo.update_knowledge_point(
            kp_id,
            subject=cand.subject,
            grade_level=cand.grade_level,
            description=(cand.definition or existing["description"] or ""),
        )
        return f"已合并到既有知识点「{cand.name}」"
    created = repo.create_knowledge_point(
        owner_id=owner_id,
        name=cand.name,
        subject=cand.subject,
        grade_level=cand.grade_level,
        description=cand.definition or "",
        difficulty=3,
        is_key_point=True,
    )
    kp_id = created["id"]

    # 前置知识点：全局按名称查找/创建，建立 kp -[:PREREQUISITE]-> pre
    created_nodes = 1
    for pre_name in (cand.prerequisites or "").replace("，", ",").split(","):
        pre_name = pre_name.strip()
        if not pre_name or pre_name == cand.name:
            continue
        pre = repo.find_by_name(pre_name, None)  # 全局查重
        if not pre:
            pre = repo.create_knowledge_point(
                owner_id=owner_id,
                name=pre_name,
                subject=cand.subject,
                grade_level=cand.grade_level,
                description="",
            )
            created_nodes += 1
        try:
            repo.create_relation(kp_id, pre["id"], "prerequisite")
        except Exception:
            pass
    return f"写入图谱节点 {created_nodes} 个"


@router.post("/candidates/{id}/approve")
def approve_candidate(
    id: uuid.UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """审核通过：写入 Neo4j 知识图谱"""
    cand = session.get(CandidateKnowledgePoint, id)
    if not cand:
        raise HTTPException(status_code=404, detail="候选知识点不存在")
    if cand.status != "pending":
        raise HTTPException(status_code=400, detail="该候选已处理")
    try:
        detail = _approve_candidate(session, cand)
    except Exception as e:
        _log(session, "candidate_review", "failed", f"审核通过写入图谱失败「{cand.name}」: {str(e)[:500]}")
        raise HTTPException(status_code=500, detail=f"写入知识图谱失败: {str(e)[:200]}")
    cand.status = "approved"
    session.add(cand)
    session.commit()
    _log(
        session,
        "candidate_review",
        "success",
        f"审核通过「{cand.name}」（{cand.kind or 'llm_extraction'}），{detail}",
    )
    return {"message": detail, "knowledge_point_id": None}


@router.post("/candidates/{id}/reject")
def reject_candidate(
    id: uuid.UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """驳回候选知识点"""
    cand = session.get(CandidateKnowledgePoint, id)
    if not cand:
        raise HTTPException(status_code=404, detail="候选知识点不存在")
    cand.status = "rejected"
    session.add(cand)
    session.commit()
    _log(session, "candidate_review", "info", f"驳回候选知识点「{cand.name}」")
    return {"message": "已驳回"}


# ==================== 批量审核 ====================


class BatchReviewRequest(BaseModel):
    ids: list[uuid.UUID]


@router.post("/candidates/batch-approve")
def batch_approve_candidates(
    *,
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
    body: BatchReviewRequest,
) -> Any:
    """批量审核通过：逐条写入 Neo4j 图谱（单条失败不影响其他）"""
    if not body.ids:
        raise HTTPException(status_code=400, detail="未选择任何候选知识点")

    approved: list[str] = []
    failed: list[dict] = []
    for cid in body.ids:
        cand = session.get(CandidateKnowledgePoint, cid)
        if not cand or cand.status != "pending":
            failed.append({"id": str(cid), "reason": "不存在或已处理"})
            continue
        try:
            _approve_candidate(session, cand)
        except Exception as e:
            failed.append({"id": str(cid), "name": cand.name, "reason": str(e)[:200]})
            _log(session, "candidate_review", "failed", f"批量审核写入图谱失败「{cand.name}」: {str(e)[:500]}")
            continue
        cand.status = "approved"
        session.add(cand)
        session.commit()
        approved.append(cand.name)

    _log(
        session,
        "candidate_review",
        "success" if not failed else "failed",
        f"批量审核通过 {len(approved)} 个候选知识点"
        + (f"，失败 {len(failed)} 个: {[f.get('name') or f['id'][:8] for f in failed]}" if failed else ""),
    )
    return {"approved": approved, "approved_count": len(approved), "failed": failed}


@router.post("/candidates/batch-reject")
def batch_reject_candidates(
    *,
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
    body: BatchReviewRequest,
) -> Any:
    """批量驳回候选知识点"""
    if not body.ids:
        raise HTTPException(status_code=400, detail="未选择任何候选知识点")

    count = 0
    for cid in body.ids:
        cand = session.get(CandidateKnowledgePoint, cid)
        if not cand or cand.status != "pending":
            continue
        cand.status = "rejected"
        session.add(cand)
        count += 1
    session.commit()
    _log(session, "candidate_review", "info", f"批量驳回 {count} 个候选知识点")
    return {"rejected_count": count}


@router.get("/graph-quality")
def graph_quality_check(
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """图谱质量检测：循环依赖 / 孤立节点 / 核心知识点缺少前置"""
    repo = KnowledgeGraphRepository()
    return repo.graph_quality_check()


# ==================== 系统任务日志 ====================


@router.get("/logs", response_model=ExtractionLogsPublic)
def list_logs(
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """系统任务日志（抽取失败/知识库更新记录）"""
    count = session.exec(select(func.count()).select_from(ExtractionLog)).one()
    statement = (
        select(ExtractionLog)
        .order_by(col(ExtractionLog.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    rows = session.exec(statement).all()
    return ExtractionLogsPublic(
        data=[ExtractionLogPublic.model_validate(r, from_attributes=True) for r in rows],
        count=count,
    )


# ==================== 教师共建建议工单（knowledge_suggestion） ====================


@router.post("/suggestions", response_model=SuggestionPublic)
def submit_suggestion(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: SuggestionCreate,
) -> Any:
    """教师端提交图谱共建建议工单（缺失知识点/纠错/误区/考点），不直接写 Neo4j"""
    sug = KnowledgeSuggestion(
        kind=body.kind,
        name=body.name,
        subject=body.subject,
        grade_level=body.grade_level,
        textbook_version=body.textbook_version,
        chapter=body.chapter,
        target_kp_id=body.target_kp_id,
        definition=body.definition,
        suggestion=body.suggestion,
        source="teacher_suggest",
        status="pending",
        submitter_id=current_user.id,
    )
    session.add(sug)
    session.commit()
    session.refresh(sug)
    _log(session, "suggestion_submit", "info", f"教师提交共建建议「{sug.name}」（{sug.kind}）")
    return SuggestionPublic.model_validate(sug, from_attributes=True)


@router.get("/suggestions")
def list_suggestions(
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
    status: str = "",
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """教师建议工单列表（与候选队列统一在管理员待审核页聚合展示）"""
    where = []
    if status:
        where.append(KnowledgeSuggestion.status == status)
    count = session.exec(
        select(func.count()).select_from(KnowledgeSuggestion).where(*where)
    ).one()
    statement = (
        select(KnowledgeSuggestion)
        .where(*where)
        .order_by(col(KnowledgeSuggestion.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    rows = session.exec(statement).all()
    return {
        "data": [SuggestionPublic.model_validate(r, from_attributes=True).model_dump() for r in rows],
        "count": count,
    }


@router.post("/suggestions/{id}/approve")
def approve_suggestion(
    id: uuid.UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """审核通过建议工单：按 kind 分发写入图谱"""
    sug = session.get(KnowledgeSuggestion, id)
    if not sug:
        raise HTTPException(status_code=404, detail="建议工单不存在")
    if sug.status != "pending":
        raise HTTPException(status_code=400, detail="该工单已处理")
    # 复用候选审核分发逻辑：构造临时候选对象
    cand = CandidateKnowledgePoint(
        name=sug.name,
        subject=sug.subject,
        grade_level=sug.grade_level,
        textbook_version=sug.textbook_version,
        definition=sug.definition,
        prerequisites=None,
        source="teacher_submit",
        status="pending",
        submitter_id=sug.submitter_id,
        kind=sug.kind,
        target_kp_id=sug.target_kp_id,
        suggestion=sug.suggestion,
    )
    try:
        detail = _approve_candidate(session, cand)
    except Exception as e:
        _log(session, "candidate_review", "failed", f"建议工单审核写入图谱失败「{sug.name}」: {str(e)[:500]}")
        raise HTTPException(status_code=500, detail=f"写入知识图谱失败: {str(e)[:200]}")
    sug.status = "approved"
    session.add(sug)
    session.commit()
    _log(session, "candidate_review", "success", f"建议工单审核通过「{sug.name}」（{sug.kind}），{detail}")
    return {"message": detail}


@router.post("/suggestions/{id}/reject")
def reject_suggestion(
    id: uuid.UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """驳回建议工单"""
    sug = session.get(KnowledgeSuggestion, id)
    if not sug:
        raise HTTPException(status_code=404, detail="建议工单不存在")
    sug.status = "rejected"
    session.add(sug)
    session.commit()
    _log(session, "candidate_review", "info", f"驳回建议工单「{sug.name}」")
    return {"message": "已驳回"}
