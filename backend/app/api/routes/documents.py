"""文档管理 API —— 上传解析 + LangGraph 抽取图写入 Neo4j 知识图谱"""
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from app.agent.graphs import run_extraction
from app.api.deps import CurrentUser, SessionDep
from app.core.db import engine
from app.file_parser import extract_text
from app.knowledge_graph import KnowledgeGraphRepository
from app.models import (
    Document,
    DocumentPublic,
    DocumentsPublic,
    DocumentStatus,
    ExtractionLog,
    KnowledgePointOut,
)

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_TYPES = {
    "text/plain": "txt",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _fetch_kps(ids: list[str]) -> dict[str, dict]:
    """批量从 Neo4j 按 ID 拉取知识点（列表页一次查询，不逐文档建连接）。

    Neo4j 故障时返回空映射——文档业务在 PG，不因图谱不可用而整体 500。
    """
    if not ids:
        return {}
    try:
        repo = KnowledgeGraphRepository()
        kps = repo.get_many_knowledge_points(ids)
    except Exception:
        return {}
    return {kp["id"]: kp for kp in kps}


def _document_to_public(
    doc: Document, kps_by_id: dict[str, dict] | None = None
) -> DocumentPublic:
    """组装文档返回体。

    kps_by_id 不传时按当前文档的知识点 ID 单独拉取（详情/上传路径）；
    列表路径由调用方批量预取后传入，避免逐文档建立 Neo4j 连接。
    """
    if kps_by_id is None:
        kps_by_id = _fetch_kps(doc.knowledge_point_ids or [])
    kps = [kps_by_id[i] for i in (doc.knowledge_point_ids or []) if i in kps_by_id]
    return DocumentPublic(
        id=doc.id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        error_message=doc.error_message,
        created_at=doc.created_at,
        owner_id=doc.owner_id,
        extracted_text=(doc.extracted_text or "")[:500] or None,
        summary=doc.summary,
        subject_id=str(doc.subject_id) if doc.subject_id else None,
        knowledge_point_ids=doc.knowledge_point_ids or [],
        knowledge_points=[KnowledgePointOut(**kp) for kp in kps],
    )


# ==================== 文档 CRUD ====================


@router.get("/", response_model=DocumentsPublic)
def read_documents(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """获取文档列表"""
    if current_user.is_superuser:
        count_statement = select(func.count()).select_from(Document)
        statement = select(Document)
    else:
        count_statement = (
            select(func.count())
            .select_from(Document)
            .where(Document.owner_id == current_user.id)
        )
        statement = select(Document).where(Document.owner_id == current_user.id)

    count = session.exec(count_statement).one()
    statement = (
        statement.order_by(col(Document.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    docs = session.exec(statement).all()
    # 批量预取知识点（一次 Neo4j 查询），图谱故障时降级为空
    all_kp_ids = sorted({i for d in docs for i in (d.knowledge_point_ids or [])})
    kps_by_id = _fetch_kps(all_kp_ids)
    return DocumentsPublic(
        data=[_document_to_public(d, kps_by_id) for d in docs],
        count=count,
    )


@router.get("/{id}", response_model=DocumentPublic)
def read_document(
    id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """获取文档详情"""
    doc = session.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not current_user.is_superuser and doc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    return _document_to_public(doc)


@router.get("/{id}/file")
def download_document(
    id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """下载原始文件（素材库预览用）"""
    from fastapi.responses import FileResponse

    doc = session.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not current_user.is_superuser and doc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已丢失")
    return FileResponse(path, filename=doc.original_filename or doc.filename)


@router.delete("/{id}")
def delete_document(
    id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> dict:
    """删除文档及其文件"""
    doc = session.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not current_user.is_superuser and doc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")

    file_path = Path(doc.file_path)
    if file_path.exists():
        file_path.unlink()

    session.delete(doc)
    session.commit()
    return {"message": "文档已删除"}


# ==================== 文件上传 ====================


@router.post("/upload", response_model=DocumentPublic)
async def upload_document(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auto_analyze: bool = True,
) -> Any:
    """上传文档文件（TXT/PDF/DOCX），自动解析文本并触发知识抽取。

    文本解析（同步，秒级）完成后立即返回；
    LangGraph 知识抽取（LLM 多轮调用，分钟级）放入后台任务执行，
    避免阻塞上传响应导致前端超时。前端按 status 轮询文档列表感知进度。
    """
    # 兼容前端 MIME 类型
    content_type = file.content_type or ""
    if "pdf" in content_type or file.filename and file.filename.endswith(".pdf"):
        content_type = "application/pdf"
    elif "docx" in content_type or "word" in content_type or (file.filename and file.filename.endswith(".docx")):
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif "text" in content_type or (file.filename and file.filename.endswith(".txt")):
        content_type = "text/plain"

    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="不支持的文件类型。支持: PDF, DOCX, TXT",
        )

    file_type = ALLOWED_TYPES[content_type]

    # 保存文件
    doc_id = uuid.uuid4()
    ext = (file.filename or "file").rsplit(".", 1)[-1] if file.filename and "." in (file.filename or "") else file_type
    if ext not in ("pdf", "docx", "txt"):
        ext = file_type
    saved_filename = f"{doc_id}.{ext}"
    file_path = UPLOAD_DIR / saved_filename

    content = await file.read()
    with open(file_path, "wb") as buffer:
        buffer.write(content)

    file_size = len(content)

    # 创建数据库记录
    doc = Document(
        id=doc_id,
        filename=saved_filename,
        original_filename=file.filename or "unknown",
        file_type=file_type,
        file_size=file_size,
        file_path=str(file_path.absolute()),
        status=DocumentStatus.UPLOADED,
        owner_id=current_user.id,
    )

    # 立即解析文本
    try:
        text = extract_text(str(file_path.absolute()), file_type)
        doc.extracted_text = text
    except Exception as e:
        doc.status = DocumentStatus.FAILED
        doc.error_message = f"文本解析失败: {str(e)}"
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return _document_to_public(doc)

    session.add(doc)
    session.commit()
    session.refresh(doc)

    # 自动触发 LangGraph 知识抽取（后台执行，不阻塞上传响应）
    if auto_analyze:
        background_tasks.add_task(
            _extraction_background,
            doc_id=str(doc.id),
            text=text,
            owner_id=str(current_user.id),
        )

    session.refresh(doc)
    return _document_to_public(doc)


def _extraction_background(doc_id: str, text: str, owner_id: str) -> None:
    """后台执行 LangGraph 抽取（独立 session，请求级 session 已随响应关闭）。

    抽取状态写入文档记录：ANALYZING → COMPLETED / FAILED，前端轮询可见。
    """
    with Session(engine) as bg_session:
        doc = bg_session.get(Document, uuid.UUID(doc_id))
        if not doc:
            return
        try:
            _run_extraction_pipeline(doc, text, uuid.UUID(owner_id), bg_session)
        except Exception as e:
            doc.status = DocumentStatus.FAILED
            doc.error_message = f"自动知识抽取失败: {str(e)[:500]}"
            bg_session.add(doc)
            bg_session.add(
                ExtractionLog(
                    task_type="document_extract",
                    status="failed",
                    message=f"文档「{doc.original_filename}」抽取失败: {str(e)[:1500]}",
                )
            )
            bg_session.commit()


def _run_extraction_pipeline(doc: Document, text: str, owner_id: uuid.UUID, session) -> dict:
    """执行 LangGraph 抽取图：识别学科 → 抽取知识点/关系 → 写入待审核队列 → 概括"""
    doc.status = DocumentStatus.ANALYZING
    session.add(doc)
    session.commit()

    result = run_extraction(
        text=text,
        owner_id=str(owner_id),
        document_id=str(doc.id),
    )

    if result.get("error"):
        raise RuntimeError(result["error"])

    # 更新文档记录（知识点 ID 引用 + 概括）
    doc.knowledge_point_ids = result.get("kp_ids", [])
    doc.summary = result.get("summary") or None
    doc.status = DocumentStatus.COMPLETED
    session.add(doc)
    session.commit()
    return result


# ==================== 知识抽取（手动触发） ====================


@router.post("/{id}/analyze", response_model=dict)
def analyze_document(
    id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """手动触发 LangGraph 知识抽取：分块 → 抽取 → 写入 Neo4j"""
    doc = session.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not current_user.is_superuser and doc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    if not doc.extracted_text:
        raise HTTPException(status_code=400, detail="文档尚未解析")

    try:
        result = _run_extraction_pipeline(doc, doc.extracted_text, current_user.id, session)
    except Exception as e:
        doc.status = DocumentStatus.FAILED
        doc.error_message = str(e)
        session.add(doc)
        session.commit()
        raise HTTPException(status_code=500, detail=f"知识抽取失败: {str(e)}")

    repo = KnowledgeGraphRepository()
    created = [repo.get_knowledge_point(kp_id) for kp_id in result.get("kp_ids", [])]
    return {
        "document": _document_to_public(doc).model_dump(),
        "extraction": {
            "subject": result.get("subject", ""),
            "knowledge_points_count": len(result.get("knowledge_points", [])),
            "relations_count": len(result.get("relations", [])),
            "knowledge_points": [
                {"id": kp["id"], "name": kp["name"], "subject": kp["subject"]}
                for kp in created if kp
            ],
            "relations": result.get("relations", []),
            "summary": result.get("summary", ""),
        },
    }


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
    """检索知识图谱节点 + 文档内容（供 AI 助手与前端搜索）"""
    repo = KnowledgeGraphRepository()
    owner_id = None if current_user.is_superuser else str(current_user.id)
    kp_results = repo.search_knowledge_points(body.query, owner_id, top_k=body.top_k)

    # 文档内容匹配
    docs = session.exec(
        select(Document).where(
            Document.owner_id == current_user.id,
            col(Document.extracted_text).is_not(None),
        )
    ).all()
    doc_results = []
    q = body.query.lower()
    for doc in docs:
        text = (doc.extracted_text or "").lower()
        if not text:
            continue
        if q in text:
            pos = text.find(q)
            doc_results.append(
                {
                    "id": str(doc.id),
                    "filename": doc.original_filename,
                    "snippet": (doc.extracted_text or "")[max(0, pos - 50) : pos + 200],
                }
            )

    return {
        "query": body.query,
        "knowledge_points": kp_results,
        "documents": doc_results[:5],
    }
