"""判分编排（FR-04/05 触发判分 + FR-06 教师终评）。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.core.config import settings
from app.grading import ai_grade, objective
from app.models import (
    QuestionGradePublic,
    QuestionGradeStatus,
    Submission,
    SubmissionGrade,
    SubmissionStatus,
)


def question_dicts(hw) -> list[dict]:
    """作业的题目列表 → dict（同为 JSON 存储，兼容 HomeworkQuestion / dict 两种形态）。"""
    return [
        q.model_dump() if hasattr(q, "model_dump") else dict(q)
        for q in (hw.questions or [])
    ]


def _to_public(g: SubmissionGrade) -> QuestionGradePublic:
    return QuestionGradePublic(
        id=g.id,
        submission_id=g.submission_id,
        question_id=g.question_id,
        question_type=g.question_type,
        full_score=g.full_score,
        is_correct=g.is_correct,
        auto_score=g.auto_score,
        auto_detail=g.auto_detail,
        ai_suggested_score=g.ai_suggested_score,
        ai_comment=g.ai_comment,
        ai_knowledge_points=g.ai_knowledge_points,
        ai_confidence=g.ai_confidence,
        needs_human=g.needs_human,
        ai_unavailable=g.ai_unavailable,
        final_score=g.final_score,
        final_comment=g.final_comment,
        finalized=g.finalized,
        finalized_at=g.finalized_at,
        status=g.status,
    )


def grade_submission(
    session: Session, submission: Submission, questions: list[dict]
) -> list[SubmissionGrade]:
    """对一份 Submission 触发判分：客观题规则判、主观题 AI 建议。

    可重入：未终评的题目覆盖重算；已终评的题目保留教师结论（FR-06 不可逆）。
    """
    qmap = {str(q.get("id")): q for q in questions}
    # 已存在的判分记录按题聚合；已终评的题目不允许被重判覆盖（FR-06 不可逆）
    existing = {
        g.question_id: g
        for g in session.exec(
            select(SubmissionGrade).where(SubmissionGrade.submission_id == submission.id)
        ).all()
    }

    grades: list[SubmissionGrade] = []
    for ans in submission.answers or []:
        qid = str(ans.get("question_id"))
        content = ans.get("content")
        q = qmap.get(qid)
        if not q:
            continue

        prev = existing.get(qid)
        if prev is not None and prev.finalized:
            # 教师已确认终评 → 保留原判，不受重判影响
            grades.append(prev)
            continue

        qtype = q.get("type")
        full = float(q.get("score") or 0.0)
        if prev is not None:
            g = prev
            # 重判：清空上一轮的判分/建议字段后重新计算
            g.is_correct = None
            g.auto_score = None
            g.auto_detail = None
            g.ai_suggested_score = None
            g.ai_comment = None
            g.ai_knowledge_points = []
            g.ai_confidence = None
            g.needs_human = False
            g.ai_unavailable = False
        else:
            g = SubmissionGrade(
                submission_id=submission.id,
                question_id=qid,
                question_type=qtype,
                full_score=full,
            )
        g.question_type = qtype
        g.full_score = full

        if qtype in ("choice", "fill"):
            res = objective.grade_objective(q, content)
            g.is_correct = res["is_correct"]
            g.auto_score = res["auto_score"]
            g.auto_detail = res["auto_detail"]
            g.ai_unavailable = False
        else:
            res = ai_grade.ai_grade_subjective(q, content)
            g.ai_suggested_score = res["ai_suggested_score"]
            g.ai_comment = res["ai_comment"]
            g.ai_knowledge_points = res["ai_knowledge_points"]
            g.ai_confidence = res["ai_confidence"]
            g.needs_human = res["needs_human"]
            # PRD §7①：AI 失败要显式标记，不能静默降级
            g.ai_unavailable = bool(res.get("ai_unavailable", False))
        g.status = QuestionGradeStatus.AUTO_GRADED
        grades.append(g)
        session.add(g)

    submission.graded_at = datetime.now(timezone.utc)
    if submission.status == SubmissionStatus.SUBMITTED:
        submission.status = SubmissionStatus.GRADED
    session.add(submission)
    session.commit()
    for g in grades:
        session.refresh(g)
    return grades


def get_grades(session: Session, submission_id) -> list[SubmissionGrade]:
    return list(
        session.exec(
            select(SubmissionGrade)
            .where(SubmissionGrade.submission_id == submission_id)
            .order_by(col(SubmissionGrade.question_id))
        ).all()
    )


def finalize_grade(
    session: Session, submission_id, question_id, req
) -> SubmissionGrade:
    """FR-06 教师终评落库（不可逆）。

    - adopt_suggestion=True：一键采纳 AI 建议
    - 否则以 final_score + final_comment 落库（手动改分 + 写评语）
    - confirm=True：二次确认后置位，后端据此放行不可逆写库
    - 已 finalized 的题目再次提交返回 409（已确认不可改）
    """
    g = session.exec(
        select(SubmissionGrade).where(
            SubmissionGrade.submission_id == submission_id,
            SubmissionGrade.question_id == question_id,
        )
    ).first()
    if not g:
        raise HTTPException(404, "未找到该题判分记录，请先触发自动判分")

    if g.finalized:
        raise HTTPException(409, "该题已确认终评，不可再修改（已确认不可改）")

    if not req.confirm:
        raise HTTPException(400, "请先在弹窗中二次确认（confirm=true）后再提交终评")

    full = g.full_score
    if req.adopt_suggestion:
        if g.ai_suggested_score is None:
            raise HTTPException(422, "该题无 AI 建议可采纳（非主观题或建议缺失）")
        # PRD §7②：低置信度 → 终评必须教师手填，禁止一键采纳
        if (
            g.ai_confidence is not None
            and g.ai_confidence < settings.AI_CONFIDENCE_HUMAN_THRESHOLD
        ):
            raise HTTPException(
                422,
                f"该题 AI 置信度 {g.ai_confidence} 低于 "
                f"{settings.AI_CONFIDENCE_HUMAN_THRESHOLD}，终评必须由教师手填，不得一键采纳",
            )
        # PRD §7①：AI 不可用时的兜底结论不是 AI 结论，同样禁止一键采纳
        if g.ai_unavailable:
            raise HTTPException(422, "AI 不可用，该题须由教师手填终评，不得一键采纳")
        final_score = g.ai_suggested_score
        final_comment = req.final_comment if req.final_comment else g.ai_comment
    else:
        if req.final_score is None:
            raise HTTPException(422, "请提供 final_score（手动改分）或设置 adopt_suggestion=true")
        final_score = req.final_score
        final_comment = req.final_comment

    if not (0.0 - 1e-9 <= final_score <= full + 1e-9):
        raise HTTPException(422, f"终评分必须在 0~{full} 之间（含）")

    g.final_score = final_score
    g.final_comment = final_comment
    g.finalized = True
    g.finalized_at = datetime.now(timezone.utc)
    g.status = QuestionGradeStatus.FINALIZED
    session.add(g)
    session.commit()
    session.refresh(g)
    return g
