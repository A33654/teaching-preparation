"""学科、教材、章节管理 API —— 章节自动同步为 Neo4j 知识点节点"""
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep
from app.knowledge_graph import KnowledgeGraphRepository
from app.models import (
    Chapter,
    ChapterCreate,
    ChapterPublic,
    ChaptersPublic,
    Document,
    DocumentPublic,
    KnowledgePointOut,
    LessonPlan,
    LessonPlanPublic,
    PptRecord,
    PptRecordPublic,
    Subject,
    SubjectCreate,
    SubjectPublic,
    SubjectsPublic,
    Textbook,
    TextbookCreate,
    TextbookPublic,
    TextbooksPublic,
)

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


def _repo() -> KnowledgeGraphRepository:
    return KnowledgeGraphRepository()


# ==================== 学科 ====================


@router.get("/subjects", response_model=SubjectsPublic)
def list_subjects(session: SessionDep, current_user: CurrentUser):
    st = select(Subject).where(Subject.owner_id == current_user.id).order_by(Subject.name)
    items = session.exec(st).all()
    return SubjectsPublic(data=[SubjectPublic.model_validate(s) for s in items], count=len(items))


@router.post("/subjects", response_model=SubjectPublic)
def create_subject(*, session: SessionDep, current_user: CurrentUser, body: SubjectCreate):
    s = Subject.model_validate(body, update={"owner_id": current_user.id})
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


@router.delete("/subjects/{sid}")
def delete_subject(sid: str, session: SessionDep, current_user: CurrentUser):
    try:
        uid = uuid.UUID(sid)
    except ValueError:
        raise HTTPException(400, "无效ID")
    s = session.get(Subject, uid)
    if not s or s.owner_id != current_user.id:
        raise HTTPException(404, "不存在")
    session.delete(s)
    session.commit()
    return {"message": "deleted"}


# ==================== 教材 ====================


@router.get("/textbooks", response_model=TextbooksPublic)
def list_textbooks(session: SessionDep, current_user: CurrentUser, subject_id: str = ""):
    st = select(Textbook).where(Textbook.owner_id == current_user.id)
    if subject_id:
        try:
            st = st.where(Textbook.subject_id == uuid.UUID(subject_id))
        except ValueError:
            pass
    st = st.order_by(Textbook.created_at.desc())
    items = session.exec(st).all()
    return TextbooksPublic(data=[TextbookPublic.model_validate(t) for t in items], count=len(items))


@router.post("/textbooks", response_model=TextbookPublic)
def create_textbook(*, session: SessionDep, current_user: CurrentUser, body: TextbookCreate):
    t = Textbook.model_validate(
        body, update={"owner_id": current_user.id, "subject_id": uuid.UUID(body.subject_id)}
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    # 自动创建根章节（教材层级）
    root = Chapter(title=t.name, level=0, textbook_id=t.id, order_index=0, owner_id=current_user.id)
    session.add(root)
    session.commit()
    return t


@router.delete("/textbooks/{tid}")
def delete_textbook(tid: str, session: SessionDep, current_user: CurrentUser):
    try:
        uid = uuid.UUID(tid)
    except ValueError:
        raise HTTPException(400, "无效ID")
    t = session.get(Textbook, uid)
    if not t or t.owner_id != current_user.id:
        raise HTTPException(404, "不存在")
    session.delete(t)
    session.commit()
    return {"message": "deleted"}


# ==================== 章节 ====================


def _build_tree(chapters: list[Chapter]) -> list[ChapterPublic]:
    """将扁平列表转为树形结构"""
    node_map = {}
    roots = []
    for ch in chapters:
        node = ChapterPublic(
            id=ch.id,
            title=ch.title,
            order_index=ch.order_index,
            level=ch.level,
            parent_id=str(ch.parent_id) if ch.parent_id else None,
            textbook_id=ch.textbook_id,
            knowledge_point_id=str(ch.knowledge_point_id) if ch.knowledge_point_id else None,
            created_at=ch.created_at,
            children=[],
        )
        node_map[str(ch.id)] = node
    for ch in chapters:
        node = node_map[str(ch.id)]
        pid = str(ch.parent_id) if ch.parent_id else None
        if pid and pid in node_map:
            node_map[pid].children.append(node)
        else:
            roots.append(node)
    return roots


@router.get("/chapters/{textbook_id}", response_model=list[ChapterPublic])
def list_chapters(textbook_id: str, session: SessionDep, current_user: CurrentUser):
    try:
        uid = uuid.UUID(textbook_id)
    except ValueError:
        raise HTTPException(400, "无效ID")
    chs = session.exec(
        select(Chapter)
        .where(Chapter.textbook_id == uid, Chapter.owner_id == current_user.id)
        .order_by(Chapter.order_index, Chapter.level)
    ).all()
    return _build_tree(chs)


@router.post("/chapters", response_model=ChapterPublic)
def create_chapter(*, session: SessionDep, current_user: CurrentUser, body: ChapterCreate):
    pid = uuid.UUID(body.parent_id) if body.parent_id else None
    tid = uuid.UUID(body.textbook_id)
    # 计算 order_index
    max_order = session.exec(
        select(func.max(col(Chapter.order_index))).where(
            Chapter.parent_id == pid, Chapter.textbook_id == tid
        )
    ).one() or 0
    ch = Chapter(
        title=body.title,
        level=body.level,
        parent_id=pid,
        textbook_id=tid,
        order_index=max_order + 1,
        owner_id=current_user.id,
    )
    session.add(ch)
    session.commit()
    session.refresh(ch)

    # 自动同步到 Neo4j 知识图谱（章节即知识点节点）
    try:
        kp = _repo().create_knowledge_point(
            owner_id=str(current_user.id),
            name=ch.title,
            subject="通用",
            description=f"教材章节: {ch.title}",
        )
        ch.knowledge_point_id = uuid.UUID(kp["id"])
        session.add(ch)
        session.commit()
    except Exception:
        pass  # Neo4j 不可用时章节仍可创建

    return ChapterPublic(
        id=ch.id,
        title=ch.title,
        order_index=ch.order_index,
        level=ch.level,
        parent_id=str(ch.parent_id) if ch.parent_id else None,
        textbook_id=ch.textbook_id,
        knowledge_point_id=str(ch.knowledge_point_id) if ch.knowledge_point_id else None,
        created_at=ch.created_at,
        children=[],
    )


@router.put("/chapters/{cid}/reorder")
def reorder_chapter(cid: str, *, session: SessionDep, current_user: CurrentUser, new_parent_id: str = "", new_order: int = 0):
    try:
        uid = uuid.UUID(cid)
    except ValueError:
        raise HTTPException(400, "无效ID")
    ch = session.get(Chapter, uid)
    if not ch or ch.owner_id != current_user.id:
        raise HTTPException(404, "不存在")
    if new_parent_id:
        try:
            ch.parent_id = uuid.UUID(new_parent_id)
        except ValueError:
            pass
    ch.order_index = new_order
    session.add(ch)
    session.commit()
    return {"message": "ok"}


@router.put("/chapters/{cid}")
def update_chapter(cid: str, *, session: SessionDep, current_user: CurrentUser, title: str = ""):
    try:
        uid = uuid.UUID(cid)
    except ValueError:
        raise HTTPException(400, "无效ID")
    ch = session.get(Chapter, uid)
    if not ch or ch.owner_id != current_user.id:
        raise HTTPException(404, "不存在")
    if title:
        ch.title = title
    session.add(ch)
    session.commit()
    # 同步更新 Neo4j 知识点节点
    if ch.knowledge_point_id:
        try:
            _repo().update_knowledge_point(str(ch.knowledge_point_id), name=ch.title)
        except Exception:
            pass
    return {"message": "ok"}


@router.delete("/chapters/{cid}")
def delete_chapter(cid: str, session: SessionDep, current_user: CurrentUser):
    try:
        uid = uuid.UUID(cid)
    except ValueError:
        raise HTTPException(400, "无效ID")
    ch = session.get(Chapter, uid)
    if not ch or ch.owner_id != current_user.id:
        raise HTTPException(404, "不存在")
    # 同步删除 Neo4j 知识点节点
    if ch.knowledge_point_id:
        try:
            _repo().delete_knowledge_point(str(ch.knowledge_point_id))
        except Exception:
            pass
    session.delete(ch)
    session.commit()
    return {"message": "deleted"}


# ==================== 学科仪表盘 ====================


@router.get("/dashboard/{subject_id}")
def subject_dashboard(subject_id: str, session: SessionDep, current_user: CurrentUser):
    try:
        sid = uuid.UUID(subject_id)
    except ValueError:
        raise HTTPException(400, "无效ID")
    subj = session.get(Subject, sid)
    if not subj:
        raise HTTPException(404, "学科不存在")

    # 相关文档
    docs = session.exec(
        select(Document)
        .where(Document.owner_id == current_user.id, Document.subject_id == sid)
        .order_by(Document.created_at.desc())
        .limit(20)
    ).all()
    # 相关教案
    lps = session.exec(
        select(LessonPlan)
        .where(LessonPlan.owner_id == current_user.id, LessonPlan.subject_id == sid)
        .order_by(LessonPlan.created_at.desc())
        .limit(20)
    ).all()
    # 相关PPT
    ppts = session.exec(
        select(PptRecord)
        .where(PptRecord.owner_id == current_user.id, PptRecord.subject_id == sid)
        .order_by(PptRecord.created_at.desc())
        .limit(20)
    ).all()
    # 相关知识点（Neo4j）
    kps = _repo().list_knowledge_points(
        owner_id=str(current_user.id), subject=subj.name, limit=50
    )[0]

    return {
        "subject": SubjectPublic.model_validate(subj).model_dump(),
        "documents": [DocumentPublic.model_validate(d).model_dump() for d in docs],
        "lesson_plans": [LessonPlanPublic.model_validate(lp).model_dump() for lp in lps],
        "ppts": [PptRecordPublic.model_validate(p).model_dump() for p in ppts],
        "knowledge_points": [KnowledgePointOut(**k).model_dump() for k in kps],
    }
