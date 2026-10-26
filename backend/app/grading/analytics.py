"""FR-07 错误聚合看板：按关联知识点统计错误率与高频错误模式。

- 班级视角：整份作业全部提交聚合
- 个人视角：单个学生的提交
- 覆盖全部关联知识点：即便某知识点暂无作答，也以 error_rate=0 出现（无遗漏）
"""
from __future__ import annotations

import uuid
from collections import defaultdict

from app.core.config import settings
from app.grading.objective import _parse_choice_index
from app.grading.service import question_dicts
from app.models import (
    ErrorDashboard,
    ErrorPattern,
    ErrorStatScope,
    KnowledgePointErrorStat,
    SubmissionGrade,
)

TOP_PATTERN_LIMIT = 3


def extract_wrong_expression(question: dict, content) -> str:
    """把一份错误作答转成可读的"错误表述"（供高频错误模式与回流建议复用的唯一实现）。

    - 选择题：误选的选项，形如「误选 C（折射）」
    - 填空/简答/论述：学生原始作答
    """
    text = content if content is not None else ""
    if not str(text).strip():
        return "（未作答）"
    if question.get("type") == "choice":
        options = question.get("options") or []
        idx = _parse_choice_index(content, options)
        if idx is not None and idx < len(options):
            return f"误选 {chr(65 + idx)}（{options[idx]}）"
        return f"作答：{text}"
    return str(text)


def is_wrong(grade: SubmissionGrade) -> bool:
    """判定一条判分是否计入「错误 / 未掌握」。

    客观题：is_correct 为 False 即错；
    主观题：优先取终评分，其次 AI 建议分，得分率 < 阈值判定为未掌握。
    """
    if grade.question_type in ("choice", "fill"):
        return grade.is_correct is False
    score = grade.final_score if grade.final_score is not None else grade.ai_suggested_score
    full = grade.full_score or 0.0
    if score is None or full <= 0:
        return False
    return (score / full) < settings.SUBJECTIVE_WRONG_SCORE_RATIO


def _resolve_kp_names(kp_ids: list[str]) -> dict[str, str]:
    """尽量从 Neo4j 解析知识点名称（无图谱时静默降级为 None）。"""
    if not kp_ids:
        return {}
    try:
        from app.knowledge_graph import KnowledgeGraphRepository

        kps = KnowledgeGraphRepository().get_many_knowledge_points(kp_ids)
        return {str(kp.get("id")): kp.get("name", "") for kp in kps}
    except Exception:
        return {}


def _resolve_kp_active(kp_ids: list[str]) -> dict[str, bool]:
    """判定知识点在图谱中是否仍存在（PRD §7⑤「已失效」标记依据）。

    返回 {kp_id: True}（仅含仍存在的知识点）。图谱不可用或查询异常时返回空 dict，
    由调用方按「未知即视为活跃」处理，避免图谱抖动把全部知识点误标失效。
    """
    if not kp_ids:
        return {}
    try:
        from app.knowledge_graph import KnowledgeGraphRepository

        kps = KnowledgeGraphRepository().get_many_knowledge_points(kp_ids)
        return {str(kp.get("id")): True for kp in kps}
    except Exception:
        return {}


def _collect_kp_ids(homework, questions: list[dict]) -> list[str]:
    """作业的全部关联知识点（题目级 ∪ 作业级），去重保序，保证"无遗漏"。"""
    kp_ids: list[str] = []
    for q in questions:
        for kp in q.get("knowledge_point_ids") or []:
            if kp not in kp_ids:
                kp_ids.append(kp)
    for kp in homework.knowledge_point_ids or []:
        if kp not in kp_ids:
            kp_ids.append(kp)
    return kp_ids


def compute_dashboard(
    session,
    homework,
    scope: ErrorStatScope = ErrorStatScope.CLASS,
    submission_id: uuid.UUID | None = None,
    submissions: list | None = None,
) -> ErrorDashboard:
    """按知识点聚合错误率与高频错误模式。

    submissions 由调用方按数据隔离规则过滤后传入（班级视角传全部，个人视角传单个）。
    """
    questions = question_dicts(homework)
    qmap = {str(q.get("id")): q for q in questions}
    kp_ids = _collect_kp_ids(homework, questions)

    subs = submissions or []
    if scope == ErrorStatScope.PERSONAL:
        subs = [s for s in subs if submission_id is None or s.id == submission_id]

    sub_ids = [s.id for s in subs]
    grades: list[SubmissionGrade] = []
    if sub_ids:
        from sqlmodel import select

        grades = list(
            session.exec(
                select(SubmissionGrade).where(
                    SubmissionGrade.submission_id.in_(sub_ids)  # type: ignore[union-attr]
                )
            ).all()
        )

    # kp → 统计
    graded = defaultdict(int)
    wrong = defaultdict(int)
    patterns = defaultdict(lambda: defaultdict(list))  # kp → expression → question_ids
    question_count = defaultdict(int)

    for q in questions:
        for kp in q.get("knowledge_point_ids") or []:
            question_count[kp] += 1

    for g in grades:
        q = qmap.get(g.question_id)
        if not q:
            continue
        kps = q.get("knowledge_point_ids") or []
        wrong_flag = is_wrong(g)
        expression = extract_wrong_expression(q, _answer_content(session, g, subs)) if wrong_flag else None
        for kp in kps:
            graded[kp] += 1
            if wrong_flag:
                wrong[kp] += 1
                patterns[kp][expression].append(g.question_id)

    # 组装（覆盖全部知识点，包括暂无作答的）
    names = _resolve_kp_names(kp_ids)
    active = _resolve_kp_active(kp_ids)
    stats: list[KnowledgePointErrorStat] = []
    for kp in kp_ids:
        gc = graded.get(kp, 0)
        wc = wrong.get(kp, 0)
        top = sorted(
            ((expr, qids) for expr, qids in patterns.get(kp, {}).items()),
            key=lambda kv: (-len(kv[1]), kv[0]),
        )[:TOP_PATTERN_LIMIT]
        stats.append(
            KnowledgePointErrorStat(
                knowledge_point_id=kp,
                knowledge_point_name=names.get(kp),
                question_count=question_count.get(kp, 0),
                graded_count=gc,
                wrong_count=wc,
                error_rate=round(wc / gc, 4) if gc else 0.0,
                # 图谱可用时以「是否查得到」为准；图谱不可用（active 为空）按活跃处理
                is_active=active.get(kp, False) if active else True,
                top_patterns=[
                    ErrorPattern(
                        expression=expr,
                        count=len(qids),
                        question_ids=sorted(set(qids)),
                    )
                    for expr, qids in top
                ],
            )
        )

    graded_sub_ids = {g.submission_id for g in grades}
    return ErrorDashboard(
        homework_id=homework.id,
        homework_title=homework.title,
        scope=scope,
        submission_id=submission_id,
        total_submissions=len(subs),
        graded_submissions=len(graded_sub_ids),
        knowledge_points=stats,
        knowledge_point_total=len(kp_ids),
    )


def _answer_content(session, grade: SubmissionGrade, subs: list):
    """取该判分记录对应的学生原始作答内容。"""
    sub = next((s for s in subs if s.id == grade.submission_id), None)
    if not sub:
        return ""
    for ans in sub.answers or []:
        if str(ans.get("question_id")) == grade.question_id:
            return ans.get("content")
    return ""
