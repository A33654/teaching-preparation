"""教案管理 API —— AI 生成走 LangGraph 教案图，知识点来自 Neo4j"""
import io
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import col, func, select

from app.agent.graphs import run_lesson_plan, run_summarize
from app.api.deps import CurrentUser, SessionDep
from app.knowledge_graph import KnowledgeGraphRepository
from app.models import (
    GradeLevel,
    KnowledgePointOut,
    LessonPlan,
    LessonPlanCreate,
    LessonPlanPublic,
    LessonPlansPublic,
    LessonPlanUpdate,
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


# CRUD
@router.get("/", response_model=LessonPlansPublic)
def read_lesson_plans(session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100):
    if current_user.is_superuser:
        cs = select(func.count()).select_from(LessonPlan)
        st = select(LessonPlan)
    else:
        cs = select(func.count()).select_from(LessonPlan).where(LessonPlan.owner_id == current_user.id)
        st = select(LessonPlan).where(LessonPlan.owner_id == current_user.id)
    count = session.exec(cs).one()
    st = st.order_by(col(LessonPlan.created_at).desc()).offset(skip).limit(limit)
    return LessonPlansPublic(data=[_lp_to_public(lp) for lp in session.exec(st).all()], count=count)


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_document(*, session: SessionDep, current_user: CurrentUser, file: UploadFile = File(...)):
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
def ai_generate_lesson_plan(*, session: SessionDep, current_user: CurrentUser, body: AILessonPlanRequest):
    """章节驱动的一键教案生成。

    教师只选章节，系统自动从 Neo4j 检索本章知识点并全部带入 Agent：
    - 图谱命中 → 基于图谱结构生成（前置依赖/重难点有据可依）
    - 图谱缺失 → 自动 RAG 兜底（基于教材文本生成，并在教案说明知识库状态）
    """
    knowledge_point_ids = list(body.knowledge_point_ids)

    # 章节自动联动：无需教师手动选择知识点（全局共享知识库，不过滤 owner）
    if not knowledge_point_ids and body.chapter:
        repo = KnowledgeGraphRepository()
        hits = repo.search_knowledge_points(
            body.chapter, owner_id=None, top_k=20
        )
        knowledge_point_ids = [h["id"] for h in hits]

    requirements = " ".join(
        x for x in [body.requirements, body.extra_context, body.summary_text] if x
    )
    if body.chapter and not knowledge_point_ids:
        requirements = (
            f"本章《{body.chapter}》知识图谱尚未收录（知识库缺失），"
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
        knowledge_point_ids=body.knowledge_point_ids,
        style=body.style or "标准",
        verification_report=verification_report,
    )
    session.add(lp)
    session.commit()
    session.refresh(lp)

    _sync_neo4j_covers(str(lp.id), body.knowledge_point_ids)

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
    if not current_user.is_superuser and lp.owner_id != current_user.id:
        raise HTTPException(403, "无权访问")
    return _lp_to_public(lp)


@router.post("/", response_model=LessonPlanPublic)
def create_lesson_plan(*, session: SessionDep, current_user: CurrentUser, lp_in: LessonPlanCreate):
    lp_data = lp_in.model_dump(exclude={"knowledge_point_ids", "subject_id"})
    lp = LessonPlan.model_validate(
        lp_data,
        update={
            "owner_id": current_user.id,
            "knowledge_point_ids": lp_in.knowledge_point_ids,
            "subject_id": uuid.UUID(lp_in.subject_id) if lp_in.subject_id else None,
        },
    )
    session.add(lp)
    session.commit()
    session.refresh(lp)
    _sync_neo4j_covers(str(lp.id), lp_in.knowledge_point_ids)
    return _lp_to_public(lp)


@router.put("/{id}", response_model=LessonPlanPublic)
def update_lesson_plan(*, session: SessionDep, current_user: CurrentUser, id: uuid.UUID, lp_in: LessonPlanUpdate):
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if not current_user.is_superuser and lp.owner_id != current_user.id:
        raise HTTPException(403, "无权访问")
    d = lp_in.model_dump(exclude_unset=True)
    kp_ids = d.pop("knowledge_point_ids", None)
    lp.sqlmodel_update(d)
    if kp_ids is not None:
        lp.knowledge_point_ids = kp_ids
        _sync_neo4j_covers(str(lp.id), kp_ids)
    session.add(lp)
    session.commit()
    session.refresh(lp)
    return _lp_to_public(lp)


@router.delete("/{id}")
def delete_lesson_plan(id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if not current_user.is_superuser and lp.owner_id != current_user.id:
        raise HTTPException(403, "无权访问")
    session.delete(lp)
    session.commit()
    return {"message": "已删除"}


@router.get("/{id}/export")
def export_lesson_plan(id: uuid.UUID, session: SessionDep, current_user: CurrentUser):
    """导出教案为 Word 文档"""
    lp = session.get(LessonPlan, id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if not current_user.is_superuser and lp.owner_id != current_user.id:
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
