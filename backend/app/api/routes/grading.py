"""判分 / 批改 API —— FR-04/05/06。

- 触发判分：客观题规则判分；主观题给出 AI 建议（不写终评）
- 查询判分：返回每题判分记录（含溯源 / AI 建议 / 终评）
- 教师终评：采纳建议或手动改分 + 写评语，二次确认后不可逆落库
- 标注集验收：FR-04 客观题自动判分准确率 ≥95% 与错判溯源
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep
from app.core import telemetry
from app.grading import labeled_set, service
from app.models import (
    FinalizeGradeRequest,
    GradeTriggerResponse,
    Homework,
    LabeledSetReport,
    QuestionGradePublic,
    Submission,
    SubmissionGradesPublic,
)

router = APIRouter(prefix="/grading", tags=["grading"])


def _get_submission(
    session: SessionDep, current_user: CurrentUser, homework_id: uuid.UUID, submission_id: uuid.UUID
) -> tuple[Homework, Submission]:
    hw = session.get(Homework, homework_id)
    if not hw:
        raise HTTPException(404, "作业不存在")
    if not current_user.is_superuser and hw.owner_id != current_user.id:
        raise HTTPException(403, "无权访问该作业")
    sub = session.get(Submission, submission_id)
    if not sub or sub.homework_id != homework_id:
        raise HTTPException(404, "提交记录不存在")
    return hw, sub


def _question_dicts(hw: Homework) -> list[dict]:
    qs = hw.questions or []
    out = []
    for q in qs:
        out.append(q.model_dump() if hasattr(q, "model_dump") else dict(q))
    return out


# ==================== FR-04/05：触发判分 ====================

@router.post(
    "/homework/{homework_id}/submissions/{submission_id}/grade",
    response_model=GradeTriggerResponse,
)
def trigger_grading(
    homework_id: uuid.UUID,
    submission_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> GradeTriggerResponse:
    """FR-04/05：触发一份提交的自动判分。

    客观题规则判分（输出得分与解析，可溯源）；
    主观题给出 AI 建议（建议分/评语/命中知识点/置信度，不写终评）；
    置信度 < 0.7 强制标记 needs_human="建议人工"。
    """
    hw, sub = _get_submission(session, current_user, homework_id, submission_id)
    grades = service.grade_submission(session, sub, _question_dicts(hw))
    return GradeTriggerResponse(
        submission_id=sub.id,
        graded_count=len(grades),
        grades=[service._to_public(g) for g in grades],
        message="判分完成：客观题已自动判分，主观题已生成 AI 建议，待教师终评。",
    )


# ==================== 查询判分结果 ====================

@router.get(
    "/homework/{homework_id}/submissions/{submission_id}/grades",
    response_model=SubmissionGradesPublic,
)
def get_grades(
    homework_id: uuid.UUID,
    submission_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> SubmissionGradesPublic:
    """查询一份提交的全部判分记录（含客观题溯源与主观题 AI 建议）。"""
    hw, sub = _get_submission(session, current_user, homework_id, submission_id)
    rows = service.get_grades(session, submission_id)
    return SubmissionGradesPublic(
        data=[service._to_public(g) for g in rows],
        count=len(rows),
        submission_status=sub.status.value,
    )


# ==================== FR-06：教师终评（不可逆） ====================

@router.post(
    "/homework/{homework_id}/submissions/{submission_id}/grades/{question_id}/finalize",
    response_model=QuestionGradePublic,
)
def finalize_grade(
    homework_id: uuid.UUID,
    submission_id: uuid.UUID,
    question_id: str,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: FinalizeGradeRequest,
) -> QuestionGradePublic:
    """FR-06：教师对单题终评。

    - adopt_suggestion=True：一键采纳 AI 建议
    - 否则以 final_score + final_comment 落库（手动改分 + 写评语）
    - confirm=True：二次确认弹窗后置位，后端据此放行不可逆写库
    - 已确认终评再次提交返回 409（已确认不可改）
    - 超管对他人作业为只读视角，写入终评返回 403（FR-10 / §9 R-1）
    """
    hw, _sub = _get_submission(session, current_user, homework_id, submission_id)
    # FR-10 数据隔离：超管可见全校聚合，但不得代写他人作业的终评
    if current_user.is_superuser and hw.owner_id != current_user.id:
        raise HTTPException(
            403, "超管为只读视角，不可写入他人作业的终评（FR-10 数据隔离）"
        )

    g = service.finalize_grade(session, submission_id, question_id, body)

    # PRD §5.3 埋点：grading_confirmed
    telemetry.emit(
        "grading_confirmed",
        homework_id=str(hw.id),
        submission_id=str(submission_id),
        question_id=question_id,
        ai_confidence=g.ai_confidence,
        adopted=bool(body.adopt_suggestion),
        user_id=str(current_user.id),
    )
    return service._to_public(g)


# ==================== FR-04：标注集验收 ====================

@router.post("/verify-labeled-set", response_model=LabeledSetReport)
def verify_labeled_set() -> LabeledSetReport:
    """FR-04 验收：标注集客观题判分准确率 ≥95%，错判可溯源。

    返回 total / correct / accuracy / passed / misjudged（错判题及其判分依据）。
    """
    report = labeled_set.run_labeled_set()
    return LabeledSetReport(**report)
