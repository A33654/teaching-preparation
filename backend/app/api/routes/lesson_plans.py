"""教案管理 API —— AI 生成走 LangGraph 教案图，知识点来自 Neo4j。

组织隔离：所有查询必须带 org_id 与权限范围（组织链 + visibility + ACL），
禁止只按 owner_id 查。状态机：draft → pending → approved/rejected → archived。
"""
import io
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import col, func, select

from app.agent.graphs import run_lesson_plan, run_summarize
from app.api.deps import CurrentUser, SessionDep
from app.core import access, contributions, rbac
from app.knowledge_graph import KnowledgeGraphRepository
from app.models import (
    ContributionType,
    GradeLevel,
    KnowledgePointOut,
    LessonPlan,
    LessonPlanCreate,
    LessonPlanPublic,
    LessonPlansPublic,
    LessonPlanSource,
    LessonPlanStatus,
    LessonPlanUpdate,
    LessonPlanVersionSnapshot,
    LessonPlanVersionSnapshotPublic,
    Organization,
    ResourceType,
    ReviewAction,
    ReviewRecord,
    Visibility,
)

router = APIRouter(prefix="/lesson-plans", tags=["lesson-plans"])


# MODELS
class AILessonPlanRequest(BaseModel):
    knowledge_point_ids: list[str] = []
    subject: str = ""
    grade_level: str = ""
    extra_context: str = ""
    style: str = ""
    requirements: str = ""
    summary_text: str = ""
    chapter: str = ""  # 章节名称：提供时自动从知识图谱检索本章知识点（无需手动选）


class SummarizeResponse(BaseModel):
    summary: str
    key_topics: list[str]
    suggested_approach: str


class GenerateResponse(BaseModel):
    id: str
    title: str
    subject: str
    grade_level: str
    teaching_objectives: str
    teaching_process: str
    key_points: list[str] = []
    difficult_points: list[str] = []
    graph_context: list[dict] = []
    raw_text: str
    verification_report: dict = {}


class RejectRequest(BaseModel):
    comment: str  # 驳回原因（必填）


class PublishToKbResponse(BaseModel):
    snapshot: LessonPlanVersionSnapshotPublic
    knowledge_item_id: str | None = None
    reference_count: int = 0


# HELPERS
def _repo() -> KnowledgeGraphRepository:
    return KnowledgeGraphRepository()


def _lp_to_public(lp: LessonPlan) -> LessonPlanPublic:
    """组装教案返回体（知识点从 Neo4j 按 ID 拉取）"""
    kps = _repo().get_many_knowledge_points(lp.knowledge_point_ids or [])
    return LessonPlanPublic(
        id=lp.id,
        title=lp.title,
        subject=lp.subject,
        grade_level=lp.grade_level,
        teaching_objectives=lp.teaching_objectives,
        teaching_process=lp.teaching_process,
        owner_id=lp.owner_id,
        org_id=lp.org_id,
        group_id=lp.group_id,
        visibility=lp.visibility,
        status=lp.status,
        source_type=lp.source_type,
        template_id=lp.template_id,
        version=lp.version,
        subject_id=str(lp.subject_id) if lp.subject_id else None,
        created_at=lp.created_at,
        knowledge_point_ids=lp.knowledge_point_ids or [],
        knowledge_points=[KnowledgePointOut(**kp) for kp in kps],
    )


def _s(v: Any) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, (dict, list)):
        import json

        return json.dumps(v, ensure_ascii=False, indent=2)
    return str(v) if v else ""


def _sync_neo4j_covers(lp_id: str, kp_ids: list[str]) -> None:
    """同步教案-知识点 COVERS 关系到 Neo4j"""
    try:
        _repo().link_lesson_plan_knowledge_points(lp_id, kp_ids)
    except Exception:
        pass  # Neo4j 不可用时不影响教案本身


def _ensure_org(session: SessionDep, user: CurrentUser) -> Organization:
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="当前用户未分配组织，无法操作")
    org = session.get(Organization, user.org_id)
    if not org:
        raise HTTPException(status_code=400, detail="组织不存在")
    return org


def _record_review(
    session: SessionDep, user: CurrentUser, lp: LessonPlan, action: ReviewAction,
    to_status: LessonPlanStatus, comment: str | None = None,
) -> None:
    rec = ReviewRecord(
        org_id=lp.org_id,
        resource_type=ResourceType.LESSON_PLAN,
        resource_id=lp.id,
        reviewer_id=user.id,
        action=action,
        from_status=lp.status.value,
        to_status=to_status.value,
        comment=comment,
    )
    session.add(rec)
    session.commit()


# CRUD
@router.get("/", response_model=LessonPlansPublic)
def read_lesson_plans(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    status: LessonPlanStatus | None = None,
) -> Any:
    """教案列表（组织作用域 + visibility + ACL 过滤；禁止只按 owner 查）。"""
    base = access.lesson_plan_candidate_filter(session, current_user)
    stmt = select(LessonPlan)
    if base is not None:
        stmt = stmt.where(base)
    if status is not None:
        stmt = stmt.where(LessonPlan.status == status)
    # 候选集（限制 1000 以内，MVP 规模足够；fine-grained 可见性在 Python 侧二次过滤）
    candidates = session.exec(
        stmt.order_by(col(LessonPlan.created_at).desc()).limit(1000)
    ).all()
    visible = [lp for lp in candidates if access.can_view_lesson_plan(session, current_user, lp)]
    page = visible[skip : skip + limit]
    return LessonPlansPublic(
        data=[_lp_to_public(lp) for lp in page],
        count=len(visible),
    )


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_document(
    *, session: SessionDep, current_user: CurrentUser, file: UploadFile = File(...)
):
    """上传文档 → LangGraph 概括图"""
    content = await file.read()
    import tempfile
    import os as _os

    ext = (file.filename or "file").rsplit(".", 1)[-1] if file.filename else "txt"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        from app.file_parser import extract_text

        text = extract_text(tmp_path, ext if ext in ("pdf", "docx", "txt") else "txt")
    finally:
        _os.unlink(tmp_path)
    if not text or len(text.strip()) < 10:
        raise HTTPException(400, "文件内容为空")
    result = run_summarize(text)
    return SummarizeResponse(
        summary=result["summary"],
        key_topics=result["key_topics"],
        suggested_approach=result["suggested_approach"],
    )


# ==================== AI GENERATE（LangGraph 教案图） ====================


@router.post("/ai-generate", response_model=GenerateResponse)
def ai_generate_lesson_plan(
    *, session: SessionDep, current_user: CurrentUser, body: AILessonPlanRequest
):
    """章节驱动的一键教案生成（带组织隔离）。"""
    org = _ensure_org(session, current_user)
    knowledge_point_ids = list(body.knowledge_point_ids)

    # 章节自动联动：按本组织知识库检索（租户隔离，不再全局共享）
    if not knowledge_point_ids and body.chapter:
        repo = KnowledgeGraphRepository()
        hits = repo.search_knowledge_points(
            body.chapter, owner_id=None, org_id=str(org.id), top_k=20
        )
        knowledge_point_ids = [h["id"] for h in hits]

    requirements = " ".join(
        x for x in [body.requirements, body.extra_context, body.summary_text] if x
    )
    if body.chapter and not knowledge_point_ids:
        requirements = (
            f"本章《{body.chapter}》知识库尚未收录（知识库缺失），"
            "请基于教材文本与通用教学法生成教案，不编造图谱依据。"
            + (" " + requirements if requirements else "")
        )

    result = run_lesson_plan(
        owner_id=str(current_user.id),
        knowledge_point_ids=knowledge_point_ids,
        subject=body.subject,
        grade_level=body.grade_level,
        requirements=requirements,
        style=body.style,
        chapter=body.chapter,
    )
    if result.get("error") or not result.get("lesson_plan"):
        raise HTTPException(500, f"教案生成失败: {result.get('error', '未知错误')}")

    verification_report = result.get("verification_report") or {}

    plan = result["lesson_plan"]

    raw_grade = _s(plan.get("grade_level", body.grade_level or ""))
    clean_grade = None
    for g in ("小学", "初中", "高中"):
        if g in raw_grade:
            clean_grade = g
            break

    key_points = plan.get("key_points", []) or []
    difficult_points = plan.get("difficult_points", []) or []
    objectives = _s(plan.get("teaching_objectives", ""))
    process = _s(plan.get("teaching_process", ""))
    if key_points:
        objectives += f"\n\n【教学重点】\n" + "\n".join(f"- {p}" for p in key_points)
    if difficult_points:
        objectives += f"\n\n【教学难点】\n" + "\n".join(f"- {p}" for p in difficult_points)

    raw_text = (
        "# " + _s(plan.get("title", "Lesson Plan")) + "\n\n"
        "**Subject**: " + _s(plan.get("subject", body.subject)) + "\n"
        "**Grade**: " + raw_grade + "\n\n"
        "## Objectives\n" + objectives + "\n\n"
        "## Teaching Process\n" + process
    )

    lp = LessonPlan(
        title=_s(plan.get("title", f"{body.subject or '通用'}教案"))[:255],
        subject=_s(plan.get("subject", body.subject or "通用")),
        grade_level=GradeLevel(clean_grade) if clean_grade else None,
        teaching_objectives=objectives,
        teaching_process=process,
        owner_id=current_user.id,
        org_id=org.id,
        visibility=Visibility.PRIVATE,
        status=LessonPlanStatus.DRAFT,
        source_type=LessonPlanSource.PERSONAL,
        knowledge_point_ids=body.knowledge_point_ids,
        style=body.style or "标准",
        verification_report=verification_report,
    )
    session.add(lp)
    session.commit()
    session.refresh(lp)

    _sync_neo4j_covers(str(lp.id), body.knowledge_point_ids)
    contributions.emit_contribution(
        session, user=current_user, event_type=ContributionType.CREATE,
        resource_type=ResourceType.LESSON_PLAN, resource_id=lp.id,
        dedupe_key=f"create:{lp.id}",
    )

    return GenerateResponse(
        id=str(lp.id),
        title=_s(plan.get("title", "")),
        subject=_s(plan.get("subject", body.subject or "")),
        grade_level=raw_grade,
        teaching_objectives=objectives,
        teaching_process=process,
        key_points=key_points,
        difficult_points=difficult_points,
        graph_context=result.get("graph_context", []),
        raw_text=raw_text,
        verification_report=verification_report,
    )


# ==================== EXPORT & CRUD ====================


@router.get("/{id}", response_model=LessonPlanPublic)
def read_lesson_plan(id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if not access.can_view_lesson_plan(session, current_user, lp):
        raise HTTPException(403, "无权访问")
    return _lp_to_public(lp)


@router.post("/", response_model=LessonPlanPublic)
def create_lesson_plan(
    *, session: SessionDep, current_user: CurrentUser, lp_in: LessonPlanCreate
):
    org = _ensure_org(session, current_user)
    lp_data = lp_in.model_dump(exclude={"knowledge_point_ids", "subject_id"})
    lp = LessonPlan.model_validate(
        lp_data,
        update={
            "owner_id": current_user.id,
            "org_id": org.id,
            "group_id": lp_in.group_id,
            "visibility": lp_in.visibility,
            "source_type": lp_in.source_type,
            "template_id": lp_in.template_id,
            "status": LessonPlanStatus.DRAFT,
            "knowledge_point_ids": lp_in.knowledge_point_ids,
            "subject_id": uuid.UUID(lp_in.subject_id) if lp_in.subject_id else None,
        },
    )
    session.add(lp)
    session.commit()
    session.refresh(lp)
    _sync_neo4j_covers(str(lp.id), lp_in.knowledge_point_ids)
    contributions.emit_contribution(
        session, user=current_user, event_type=ContributionType.CREATE,
        resource_type=ResourceType.LESSON_PLAN, resource_id=lp.id,
        dedupe_key=f"create:{lp.id}",
    )
    return _lp_to_public(lp)


@router.put("/{id}", response_model=LessonPlanPublic)
def update_lesson_plan(
    *, session: SessionDep, current_user: CurrentUser, id: uuid.UUID, lp_in: LessonPlanUpdate
):
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    # 只有草稿本人（或 ACL 编辑/超管）可改；教师只能改自己草稿
    if not access.can_edit_lesson_plan(session, current_user, lp):
        raise HTTPException(403, "仅本人草稿（或获编辑授权者）可修改")
    d = lp_in.model_dump(exclude_unset=True)
    kp_ids = d.pop("knowledge_point_ids", None)
    group_id = d.pop("group_id", None)
    visibility = d.pop("visibility", None)
    source_type = d.pop("source_type", None)
    classroom_exercises = d.pop("classroom_exercises", None)
    lp.sqlmodel_update(d)
    if group_id is not None:
        lp.group_id = group_id
    if visibility is not None:
        lp.visibility = visibility
    if source_type is not None:
        lp.source_type = source_type
    if kp_ids is not None:
        lp.knowledge_point_ids = kp_ids
        _sync_neo4j_covers(str(lp.id), kp_ids)
    if classroom_exercises is not None:
        lp.classroom_exercises = classroom_exercises
    session.add(lp)
    session.commit()
    session.refresh(lp)
    return _lp_to_public(lp)


@router.delete("/{id}")
def delete_lesson_plan(id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if not access.can_edit_lesson_plan(session, current_user, lp):
        raise HTTPException(403, "仅本人草稿（或获编辑授权者）可删除")
    session.delete(lp)
    session.commit()
    return {"message": "已删除"}


@router.get("/{id}/export")
def export_lesson_plan(id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """导出教案为 Word 文档"""
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if not access.can_view_lesson_plan(session, current_user, lp):
        raise HTTPException(403, "无权访问")
    from app.core.lesson_export import export_lesson_plan_to_docx

    lp_data = _lp_to_public(lp).model_dump(mode="json")
    docx_bytes = export_lesson_plan_to_docx(lp_data)
    safe_name = lp.title.replace(" ", "_").replace("/", "_")[:50]
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}.docx"},
    )


# ==================== 审核状态机 ====================
# draft → pending → approved/rejected → archived；驳回带原因，可重新提交。


def _get_owned_or_403(session, current_user, id) -> LessonPlan:
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if not current_user.is_superuser and lp.owner_id != current_user.id:
        raise HTTPException(403, "仅创建人可操作")
    return lp


@router.post("/{id}/submit", response_model=LessonPlanPublic)
def submit_lesson_plan(id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """提交审核：draft/rejected → pending（仅创建人）"""
    lp = _get_owned_or_403(session, current_user, id)
    if lp.status not in (LessonPlanStatus.DRAFT, LessonPlanStatus.REJECTED):
        raise HTTPException(400, f"当前状态 {lp.status.value} 不可提交")
    _record_review(session, current_user, lp, ReviewAction.SUBMIT, LessonPlanStatus.PENDING)
    lp.status = LessonPlanStatus.PENDING
    session.add(lp)
    session.commit()
    session.refresh(lp)
    contributions.emit_contribution(
        session, user=current_user, event_type=ContributionType.SUBMIT,
        resource_type=ResourceType.LESSON_PLAN, resource_id=lp.id,
        dedupe_key=f"submit:{lp.id}:{contributions.current_period()}",
    )
    return _lp_to_public(lp)


@router.post("/{id}/approve", response_model=LessonPlanPublic)
def approve_lesson_plan(
    id: uuid.UUID,
    session: SessionDep,
    current_user: rbac.RequireReview,
):
    """审核通过：pending → approved（需审核权限）"""
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if lp.status != LessonPlanStatus.PENDING:
        raise HTTPException(400, f"当前状态 {lp.status.value} 不可审核通过")
    _record_review(session, current_user, lp, ReviewAction.APPROVE, LessonPlanStatus.APPROVED)
    lp.status = LessonPlanStatus.APPROVED
    lp.version += 1
    session.add(lp)
    session.commit()
    session.refresh(lp)
    # 贡献记在作者身上
    from app.models import User

    author = session.get(User, lp.owner_id)
    if author:
        contributions.emit_contribution(
            session, user=author, event_type=ContributionType.APPROVE,
            resource_type=ResourceType.LESSON_PLAN, resource_id=lp.id,
            dedupe_key=f"approve:{lp.id}",
        )
    return _lp_to_public(lp)


@router.post("/{id}/reject", response_model=LessonPlanPublic)
def reject_lesson_plan(
    id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: rbac.RequireReview,
    body: RejectRequest,
):
    """审核驳回：pending → rejected（需审核权限，必填原因）"""
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if lp.status != LessonPlanStatus.PENDING:
        raise HTTPException(400, f"当前状态 {lp.status.value} 不可驳回")
    if not body.comment or not body.comment.strip():
        raise HTTPException(400, "驳回原因必填")
    _record_review(
        session, current_user, lp, ReviewAction.REJECT, LessonPlanStatus.REJECTED,
        comment=body.comment.strip(),
    )
    lp.status = LessonPlanStatus.REJECTED
    session.add(lp)
    session.commit()
    session.refresh(lp)
    return _lp_to_public(lp)


@router.post("/{id}/resubmit", response_model=LessonPlanPublic)
def resubmit_lesson_plan(id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """重新提交：rejected → pending（仅创建人）"""
    lp = _get_owned_or_403(session, current_user, id)
    if lp.status != LessonPlanStatus.REJECTED:
        raise HTTPException(400, f"当前状态 {lp.status.value} 不可重新提交")
    _record_review(session, current_user, lp, ReviewAction.RESUBMIT, LessonPlanStatus.PENDING)
    lp.status = LessonPlanStatus.PENDING
    session.add(lp)
    session.commit()
    session.refresh(lp)
    return _lp_to_public(lp)


@router.post("/{id}/archive", response_model=LessonPlanPublic)
def archive_lesson_plan(
    id: uuid.UUID,
    session: SessionDep,
    current_user: rbac.RequireReview,
):
    """归档：approved → archived（需审核权限）"""
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if lp.status != LessonPlanStatus.APPROVED:
        raise HTTPException(400, f"当前状态 {lp.status.value} 不可归档")
    _record_review(session, current_user, lp, ReviewAction.ARCHIVE, LessonPlanStatus.ARCHIVED)
    lp.status = LessonPlanStatus.ARCHIVED
    session.add(lp)
    session.commit()
    session.refresh(lp)
    return _lp_to_public(lp)


@router.post("/{id}/publish-to-kb", response_model=PublishToKbResponse)
def publish_lesson_plan_to_kb(
    id: uuid.UUID,
    session: SessionDep,
    current_user: rbac.RequireKbManage,
):
    """入知识库：生成版本快照（冻结正文），并在本组织 Neo4j 中创建知识条目引用该快照。

    知识库条目只引用快照，不直接复制正文；记录引用次数。
    """
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if lp.status != LessonPlanStatus.APPROVED:
        raise HTTPException(400, "仅已通过审核的教案可入知识库")
    # 快照版本号 = 当前 version（入库后 version 不再递增，避免与审核版本混淆）
    snapshot_json = {
        "title": lp.title,
        "subject": lp.subject,
        "grade_level": lp.grade_level.value if lp.grade_level else None,
        "teaching_objectives": lp.teaching_objectives,
        "teaching_process": lp.teaching_process,
        "knowledge_point_ids": lp.knowledge_point_ids or [],
        "owner_id": str(lp.owner_id),
    }
    snapshot = LessonPlanVersionSnapshot(
        lesson_plan_id=lp.id,
        org_id=lp.org_id,
        version=lp.version,
        snapshot_json=snapshot_json,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)

    # 在 Neo4j 创建知识条目（本组织隔离），引用快照
    kp_id = None
    ref_count = 1
    try:
        repo = KnowledgeGraphRepository()
        node = repo.create_knowledge_item(
            org_id=str(lp.org_id),
            owner_id=str(current_user.id),
            name=lp.title,
            subject=lp.subject,
            grade_level=lp.grade_level.value if lp.grade_level else None,
            description=(lp.teaching_objectives or "")[:2000],
            snapshot_id=str(snapshot.id),
            source="lesson_plan",
        )
        kp_id = node.get("id")
    except Exception:
        pass  # Neo4j 不可用时仍保留快照

    contributions.emit_contribution(
        session, user=current_user, event_type=ContributionType.REFERENCE,
        resource_type=ResourceType.KNOWLEDGE_ITEM, resource_id=snapshot.id,
        dedupe_key=f"kb:{lp.id}",
    )
    return PublishToKbResponse(
        snapshot=LessonPlanVersionSnapshotPublic(
            id=snapshot.id,
            lesson_plan_id=snapshot.lesson_plan_id,
            org_id=snapshot.org_id,
            version=snapshot.version,
            created_at=snapshot.created_at,
            snapshot_json=snapshot.snapshot_json,
        ),
        knowledge_item_id=kp_id,
        reference_count=ref_count,
    )
