"""学情分析与导出 API —— FR-07/08/09 + 数据隔离。

- FR-07 错误聚合看板：按关联知识点统计错误率与 TOP 高频错误模式（班级/个人视角）
- FR-08 误区回流：达标知识点推送建议卡片，教师确认后写入图谱误区（来源「教学回流」）
- FR-09 脱敏导出：Excel / PDF，仅含学号哈希与派生匿名昵称

数据隔离：
- 教师仅可见本人发布的作业及其提交（非本人 → 403）
- 超管可见全校作业聚合；因学号入库即哈希且导出仅含哈希，超管同样接触不到个人明文
"""
from __future__ import annotations

import os
import tempfile
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import col, select
from starlette.background import BackgroundTask

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.grading.analytics import compute_dashboard
from app.grading.backflow import build_suggestions, confirm_backflow
from app.grading.export_service import build_export_rows, write_pdf, write_xlsx
from app.models import (
    BackflowConfirmRequest,
    ErrorDashboard,
    ErrorStatScope,
    Homework,
    MisconceptionOut,
    MisconceptionSuggestions,
    Submission,
    SubmissionGrade,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _get_homework(session: SessionDep, current_user: CurrentUser, homework_id: uuid.UUID) -> Homework:
    """数据隔离：教师只能访问自己发布的作业。"""
    hw = session.get(Homework, homework_id)
    if not hw:
        raise HTTPException(404, "作业不存在")
    if not current_user.is_superuser and hw.owner_id != current_user.id:
        raise HTTPException(403, "无权访问该作业")
    return hw


def _load_submissions(session: SessionDep, homework_id: uuid.UUID) -> list[Submission]:
    return list(
        session.exec(
            select(Submission)
            .where(Submission.homework_id == homework_id)
            .order_by(col(Submission.submitted_at))
        ).all()
    )


def _load_grades(session: SessionDep, sub_ids: list[uuid.UUID]) -> list[SubmissionGrade]:
    if not sub_ids:
        return []
    return list(
        session.exec(
            select(SubmissionGrade).where(
                SubmissionGrade.submission_id.in_(sub_ids)  # type: ignore[union-attr]
            )
        ).all()
    )


# ==================== FR-07：错误聚合看板 ====================

@router.get("/homework/{homework_id}/dashboard", response_model=ErrorDashboard)
def error_dashboard(
    homework_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    scope: str = "class",
    submission_id: uuid.UUID | None = None,
) -> ErrorDashboard:
    """FR-07：按关联知识点统计错误率与高频错误模式。

    scope=class 班级视角（全部提交聚合）；scope=personal 个人视角（指定 submission_id）。
    返回中 knowledge_points 覆盖该作业的全部关联知识点（含暂无作答的），确保无遗漏。
    """
    try:
        stat_scope = ErrorStatScope(scope)
    except ValueError:
        raise HTTPException(400, "scope 仅支持 class / personal") from None

    hw = _get_homework(session, current_user, homework_id)
    subs = _load_submissions(session, homework_id)

    if stat_scope == ErrorStatScope.PERSONAL:
        if submission_id is None:
            raise HTTPException(400, "个人视角必须提供 submission_id")
        if not any(s.id == submission_id for s in subs):
            raise HTTPException(404, "提交记录不存在或不属于该作业")

    return compute_dashboard(
        session, hw, stat_scope, submission_id=submission_id, submissions=subs
    )


# ==================== FR-08：误区回流建议与确认 ====================

@router.get(
    "/homework/{homework_id}/misconception-suggestions",
    response_model=MisconceptionSuggestions,
)
def misconception_suggestions(
    homework_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    threshold: float | None = None,
) -> MisconceptionSuggestions:
    """FR-08：错误率 ≥ 阈值的知识点 → 建议补入图谱误区卡片（附典型错误表述）。

    threshold 缺省取 settings.MISCONCEPTION_BACKFLOW_THRESHOLD（默认 0.4）。
    """
    if threshold is not None and not 0.0 <= threshold <= 1.0:
        raise HTTPException(400, "threshold 需在 0~1 之间")
    hw = _get_homework(session, current_user, homework_id)
    subs = _load_submissions(session, homework_id)
    return build_suggestions(session, hw, subs, threshold)


@router.post(
    "/homework/{homework_id}/misconception-backflow", response_model=MisconceptionOut
)
def confirm_misconception_backflow(
    homework_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: BackflowConfirmRequest,
) -> MisconceptionOut:
    """FR-08：教师确认回流 → 知识点新增一条经审核的误区记录，来源标注「教学回流」。"""
    hw = _get_homework(session, current_user, homework_id)
    return confirm_backflow(session, hw, body, current_user)


# ==================== FR-09：脱敏导出 ====================

@router.get("/homework/{homework_id}/export")
def export_grading(
    homework_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    format: str = "xlsx",
    scope: str = "class",
    submission_id: uuid.UUID | None = None,
) -> FileResponse:
    """FR-09：导出成绩与批改明细（xlsx / pdf），仅含学号哈希与派生匿名昵称。"""
    fmt = (format or "xlsx").lower()
    if fmt not in _MEDIA_TYPES:
        raise HTTPException(400, "format 仅支持 xlsx / pdf")

    hw = _get_homework(session, current_user, homework_id)
    subs = _load_submissions(session, homework_id)

    if scope == "personal":
        if submission_id is None:
            raise HTTPException(400, "个人导出必须提供 submission_id")
        if not any(s.id == submission_id for s in subs):
            raise HTTPException(404, "提交记录不存在或不属于该作业")
    elif scope != "class":
        raise HTTPException(400, "scope 仅支持 class / personal")

    target_subs = [s for s in subs if scope != "personal" or s.id == submission_id]
    grades = _load_grades(session, [s.id for s in target_subs])
    summary, detail = build_export_rows(hw, target_subs, grades)

    suffix = f".{fmt}"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    try:
        if fmt == "pdf":
            write_pdf(tmp.name, hw.title, summary, detail)
        else:
            write_xlsx(tmp.name, hw.title, summary, detail)
    except Exception as exc:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise HTTPException(500, f"导出文件生成失败：{exc}") from exc

    return FileResponse(
        tmp.name,
        filename=f"grading-{homework_id}{suffix}",
        media_type=_MEDIA_TYPES[fmt],
        background=BackgroundTask(os.unlink, tmp.name),
    )
