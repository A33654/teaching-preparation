"""主观题（简答 / 论述）AI 辅助建议 —— FR-05。

优先调用 LLM（结构化输出）；任何失败（无 Key / 网络异常 / 解析失败）均回退到
确定性的离线启发式评分，保证功能在无外部服务时仍可用、可测。

输出：建议分、批改评语、命中知识点、置信度(0-1)；
      置信度 < 0.7 强制标记 needs_human（"建议人工"）。
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.core.config import settings


def _tokenize(text: str) -> set[str]:
    """极简中英文分词：英文/数字按词，中文按字符 + 二元组。"""
    text = (text or "").strip()
    if not text:
        return set()
    tokens = set(re.findall(r"[a-zA-Z0-9]+", text.lower()))
    cn = re.sub(r"[^一-鿿]", "", text)
    for ch in cn:
        tokens.add(ch)
    for i in range(len(cn) - 1):
        tokens.add(cn[i : i + 2])
    return tokens


def _heuristic(question: dict, content) -> dict:
    full = float(question.get("score") or 0.0)
    reference = question.get("reference_answer") or ""
    student = content if isinstance(content, str) else (str(content) if content is not None else "")
    kps = list(question.get("knowledge_point_ids") or [])

    if not student.strip():
        return {
            "ai_suggested_score": 0.0,
            "ai_comment": "学生未作答，建议给 0 分，请教师确认。",
            "ai_knowledge_points": kps,
            "ai_confidence": 0.30,
            "needs_human": True,
        }

    ref_tokens = _tokenize(reference)
    stu_tokens = _tokenize(student)
    if ref_tokens:
        hit = len(ref_tokens & stu_tokens) / len(ref_tokens)
    else:
        # 无参考答案时，以作答长度粗略估计重合度
        hit = min(1.0, len(student) / max(1, len(reference) if reference else 20))

    ratio = max(0.0, min(1.0, hit))
    suggested = round(ratio * full, 1)
    # 置信度：重合度高且作答充分 → 高；低重合或作答过短 → 低（<0.7 触发人工）
    penalty = 0.0 if len(student) >= 8 else 0.15
    confidence = round(max(0.30, min(0.98, 0.45 + 0.5 * ratio - penalty)), 2)
    needs_human = confidence < settings.AI_CONFIDENCE_HUMAN_THRESHOLD

    pct = int(ratio * 100)
    if ratio >= 0.8:
        level = "命中全部核心要点"
    elif ratio >= 0.4:
        level = "部分命中要点"
    else:
        level = "要点缺失较多"
    comment = (
        f"与参考答案要点重合度约 {pct}%。{level}，建议给分 {suggested}/{full}。"
        + ("建议教师复核后确认终评。" if needs_human else "")
    )
    return {
        "ai_suggested_score": suggested,
        "ai_comment": comment,
        "ai_knowledge_points": kps,
        "ai_confidence": confidence,
        "needs_human": needs_human,
    }


def _llm_grade(question: dict, content) -> dict | None:
    """调用 LLM 结构化输出；任何失败返回 None，由上层回退启发式。"""
    try:
        from app.agent.llm import _provider_candidates, get_structured_model
    except Exception:
        return None
    if not _provider_candidates():
        return None

    class AISuggestion(BaseModel):
        suggested_score: float = Field(..., description="建议分，0~满分之间")
        comment: str = Field(..., description="批改评语")
        knowledge_points: list[str] = Field(default_factory=list, description="命中知识点名称")
        confidence: float = Field(..., ge=0.0, le=1.0, description="置信度 0-1")

    reference = question.get("reference_answer") or ""
    full = float(question.get("score") or 0.0)
    kps = list(question.get("knowledge_point_ids") or [])
    student = content if isinstance(content, str) else (str(content) if content is not None else "")

    system = (
        "你是严谨的阅卷教师。依据参考答案，对学生主观作答给出建议分、评语、"
        "命中知识点与置信度。置信度低（不确定）时如实在 0-0.6 区间给出。"
    )
    user = (
        f"题目（满分 {full} 分）：{question.get('stem', '')}\n"
        f"参考答案：{reference}\n"
        f"学生作答：{student}\n"
        f"关联知识点 ID：{', '.join(kps) if kps else '无'}\n"
        "请输出结构化建议。"
    )
    try:
        model = get_structured_model(AISuggestion, temperature=0.2)
        result = model.invoke({"messages": [{"role": "system", "content": system},
                                            {"role": "user", "content": user}]})
        if not isinstance(result, AISuggestion):
            return None
        suggested = max(0.0, min(full, float(result.suggested_score)))
        confidence = max(0.0, min(1.0, float(result.confidence)))
        return {
            "ai_suggested_score": round(suggested, 1),
            "ai_comment": result.comment or "",
            # LLM 返回的是知识点名称；这里存储为 ID 占位不便，统一回退到题目自带 ID
            "ai_knowledge_points": kps,
            "ai_confidence": round(confidence, 2),
            "needs_human": confidence < settings.AI_CONFIDENCE_HUMAN_THRESHOLD,
        }
    except Exception:
        return None


def ai_grade_subjective(question: dict, content) -> dict:
    """主观题 AI 辅助建议：先试 LLM，失败回退离线启发式。

    PRD §7①：AI 调用失败（超时 / 异常）时必须**显式标记**「AI 不可用，转人工」
    （ai_unavailable=True 且评语前置提示），不能把启发式兜底静默当成 AI 结论。
    """
    try:
        llm_res = _llm_grade(question, content)
    except Exception:  # noqa: BLE001 - AI 可用性问题不应阻断整份作业的判分
        llm_res = None
        unavailable = True
    else:
        unavailable = False

    if llm_res is not None:
        res = dict(llm_res)
    else:
        res = dict(_heuristic(question, content))

    if unavailable:
        res["ai_unavailable"] = True
        res["needs_human"] = True
        res["ai_comment"] = (
            "AI 不可用，转人工：" + (res.get("ai_comment") or "")
        ).strip()
    else:
        res.setdefault("ai_unavailable", False)
    return res
