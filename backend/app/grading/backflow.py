"""FR-08 误区回流建议与确认。

对错误率 ≥ 阈值（默认 40%，settings.MISCONCEPTION_BACKFLOW_THRESHOLD 可配）的知识点，
推送「建议补入图谱误区」卡片并附带典型错误表述；
教师确认后写入该知识点的误区节点 + 纠正，且来源标注「教学回流」。
"""
from __future__ import annotations

from fastapi import HTTPException

from app.core import telemetry
from app.core.config import settings
from app.grading.analytics import compute_dashboard
from app.grading.service import question_dicts
from app.models import (
    BackflowConfirmRequest,
    ErrorStatScope,
    MisconceptionOut,
    MisconceptionSuggestion,
    MisconceptionSuggestions,
    MistakeFeedback,
    MistakeFeedbackStatus,
)

# 来源标注：Neo4j 节点与接口返回均使用同一中文标签，便于端到端校验
BACKFLOW_SOURCE = "教学回流"


def derive_correction(homework, knowledge_point_id: str) -> str:
    """由该知识点关联的题目标准答案推导「纠正」文案。"""
    corrections: list[str] = []
    for q in question_dicts(homework):
        if knowledge_point_id not in (q.get("knowledge_point_ids") or []):
            continue
        if q.get("type") == "choice":
            idx = q.get("correct_option")
            opts = q.get("options") or []
            if isinstance(idx, int) and 0 <= idx < len(opts):
                corrections.append(f"{chr(65 + idx)}（{opts[idx]}）")
        elif q.get("answers"):
            corrections.append(" / ".join(str(a) for a in q["answers"]))
        elif q.get("reference_answer"):
            corrections.append(str(q["reference_answer"]))
    return "；".join(dict.fromkeys(corrections))[:300]


def build_suggestions(
    session, homework, submissions: list, threshold: float | None = None
) -> MisconceptionSuggestions:
    """列出错误率达标、建议补入图谱误区的知识点卡片。"""
    th = settings.MISCONCEPTION_BACKFLOW_THRESHOLD if threshold is None else threshold
    dash = compute_dashboard(
        session, homework, ErrorStatScope.CLASS, submissions=submissions
    )

    data: list[MisconceptionSuggestion] = []
    for stat in dash.knowledge_points:
        if not stat.graded_count or stat.error_rate < th:
            continue
        exprs = [p.expression for p in stat.top_patterns]
        content = (
            f"典型错误：{'；'.join(exprs[:3])}" if exprs else "该知识点错误率偏高，建议补充误区记录"
        )
        data.append(
            MisconceptionSuggestion(
                knowledge_point_id=stat.knowledge_point_id,
                knowledge_point_name=stat.knowledge_point_name,
                error_rate=stat.error_rate,
                wrong_count=stat.wrong_count,
                graded_count=stat.graded_count,
                threshold=th,
                typical_expressions=exprs,
                suggested_content=content[:300],
                suggested_correction=derive_correction(homework, stat.knowledge_point_id),
            )
        )

    data.sort(key=lambda s: (-s.error_rate, s.knowledge_point_id))
    return MisconceptionSuggestions(data=data, count=len(data), threshold=th)


def confirm_backflow(session, homework, req: BackflowConfirmRequest, current_user) -> MisconceptionOut:
    """教师确认回流 → 写入知识点误区（+纠正），来源标注「教学回流」且记录审核人。

    - PRD §9 R-2：幂等 —— 同一作业 + 同一知识点 + 同一表述已确认过则直接返回，
      不重复写入图谱（避免重复确认产生重复误区节点）。
    - 知识点不存在时前置返回 404，避免产生孤儿误区节点。
    """
    from datetime import datetime, timezone

    from sqlmodel import select

    content = (req.content or "").strip()
    if not content:
        raise HTTPException(422, "误区表述（content）不能为空")

    # ---- 幂等守卫：查已有 CONFIRMED 留痕 ----
    existing = session.exec(
        select(MistakeFeedback).where(
            MistakeFeedback.homework_id == homework.id,
            MistakeFeedback.knowledge_point_id == req.knowledge_point_id,
            MistakeFeedback.content == content,
            MistakeFeedback.status == MistakeFeedbackStatus.CONFIRMED,
        )
    ).first()
    if existing is not None:
        telemetry.emit(
            "mistake_feedback_decided",
            homework_id=str(homework.id),
            knowledge_point_id=req.knowledge_point_id,
            decision="confirmed",
            idempotent=True,
            user_id=str(current_user.id),
        )
        return MisconceptionOut(
            id=existing.misconception_id,
            content=existing.content,
            correction=existing.correction,
            source=BACKFLOW_SOURCE,
        )

    from app.knowledge_graph import KnowledgeGraphRepository

    repo = KnowledgeGraphRepository()

    kp = None
    try:
        kp = repo.get_knowledge_point(req.knowledge_point_id)
    except Exception as exc:  # 图谱不可用时明确报错，而不是静默造孤儿数据
        raise HTTPException(503, f"知识图谱不可用：{exc}") from exc
    if not kp:
        raise HTTPException(404, "知识点不存在，无法回流")

    correction = (req.correction or "").strip() or derive_correction(
        homework, req.knowledge_point_id
    )

    mis = repo.create_misconception(
        owner_id=str(current_user.id),
        content=content,
        correction=correction,
        source=BACKFLOW_SOURCE,
        reviewed_by=str(current_user.id),
    )
    repo.link_kp_misconception(req.knowledge_point_id, mis["id"])

    # 留痕（同时作为下次确认的幂等键）
    session.add(
        MistakeFeedback(
            homework_id=homework.id,
            knowledge_point_id=req.knowledge_point_id,
            content=content,
            correction=correction,
            misconception_id=str(mis["id"]),
            status=MistakeFeedbackStatus.CONFIRMED,
            decided_by=current_user.id,
            decided_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    telemetry.emit(
        "mistake_feedback_decided",
        homework_id=str(homework.id),
        knowledge_point_id=req.knowledge_point_id,
        decision="confirmed",
        idempotent=False,
        user_id=str(current_user.id),
    )

    return MisconceptionOut(
        id=mis["id"],
        content=mis["content"],
        correction=mis.get("correction", correction),
        source=BACKFLOW_SOURCE,
    )
