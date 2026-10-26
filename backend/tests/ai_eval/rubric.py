# -*- coding: utf-8 -*-
"""L3 AI 评测：规则化 rubric 评分（离线可执行，无需真实 LLM）。

设计目标（见 docs/testing/测试执行计划.md）：
  - 对 AI 生成产物（教案 / 文档概括 / 教学问答）做多维度 rubric 评分
  - 每个维度 0~5 分，按权重汇总为 0~5 的总体分
  - 合格线：overall >= 4.0 / 5.0

说明：完整「LLM-as-Judge」需在具备 LLM Key 的环境运行；沙箱内以确定性
规则检查替代，覆盖结构完整、无错误标记、知识库可追溯、语言恰当、学段合理、
安全合规六个维度，作为可回归的自动化 AI 质量门禁。
"""
from __future__ import annotations

import re

# 错误/失败标记（生成产物不应包含这些）
_ERROR_MARKERS = ("错误", "失败", "error", "exception", "traceback", "未生成", "无法生成")
# 常见 PII 模式（安全合规检查）
_PII_PATTERNS = [
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),          # email
    re.compile(r"\b1[3-9]\d{9}\b"),                       # 手机号
    re.compile(r"\b\d{15,18}[Xx]?\b"),                    # 身份证号
]
_CJK = re.compile(r"[一-鿿]")


def has_cjk(text: str) -> bool:
    return bool(_CJK.search(text or ""))


def has_error_marker(text: str) -> bool:
    t = (text or "").lower()
    return any(m.lower() in t for m in _ERROR_MARKERS)


def has_pii(text: str) -> bool:
    t = text or ""
    return any(p.search(t) for p in _PII_PATTERNS)


def _grade_resolved(grade_level) -> bool:
    if grade_level is None:
        return False
    return str(grade_level) in ("小学", "初中", "高中", "小", "初", "高")


class Criterion:
    """单个评分维度。score(artifact, meta) -> (0~5 分, 说明)。"""

    def __init__(self, key: str, weight: float, description: str,
                 fn) -> None:
        self.key = key
        self.weight = weight
        self.description = description
        self.fn = fn

    def score(self, art, meta):
        return self.fn(art, meta)


class AIRubric:
    """AI 产物质量 rubric。"""

    def __init__(self) -> None:
        self.criteria: list[Criterion] = [
            Criterion(
                "structure", 0.25, "结构完整：必含标题/目标/过程（教案）、摘要/要点（概括）、非空回复（问答）",
                self._structure,
            ),
            Criterion(
                "no_error", 0.20, "无错误标记：产物不含 错误/失败/exception 等失败信号",
                self._no_error,
            ),
            Criterion(
                "kb_grounding", 0.20, "知识库可追溯：提供章节时引用了知识点；问答带来源",
                self._kb_grounding,
            ),
            Criterion(
                "language", 0.15, "语言恰当：中文语境下含中文字符、无明显乱码",
                self._language,
            ),
            Criterion(
                "grade_resolved", 0.10, "学段合理：grade_level 解析为 小学/初中/高中",
                self._grade_resolved,
            ),
            Criterion(
                "safety", 0.10, "安全合规：不含 PII（邮箱/手机号/身份证）泄漏",
                self._safety,
            ),
        ]

    # ---------------- 各维度打分 ----------------
    @staticmethod
    def _structure(art, meta):
        kind = art.get("kind")
        if kind == "lesson_plan":
            ok = art.get("title") and art.get("teaching_objectives") and art.get("teaching_process")
            return (5 if ok else (3 if art.get("title") else 0), "教案结构")
        if kind == "summary":
            ok = art.get("summary") and art.get("key_topics")
            return (5 if ok else (2 if art.get("summary") else 0), "概括结构")
        if kind == "chat_reply":
            return (5 if art.get("reply") else 0, "问答非空")
        return (3, "未知类型")

    @staticmethod
    def _no_error(art, meta):
        blob = " ".join(str(v) for v in art.values() if isinstance(v, (str, list)))
        return (0 if has_error_marker(blob) else 5, "错误标记检查")

    @staticmethod
    def _kb_grounding(art, meta):
        if art.get("kind") == "chat_reply":
            return (5 if art.get("sources") else 2, "问答来源")
        # 教案/概括：若提供了章节且知识库命中，应引用知识点名
        refs = art.get("references_kp") or False
        return (5 if refs else (3 if meta.get("kb_expected") else 4), "知识点引用")

    @staticmethod
    def _language(art, meta):
        text = art.get("text") or art.get("reply") or art.get("summary") or ""
        return (5 if has_cjk(text) else 2, "中文检查")

    @staticmethod
    def _grade_resolved(art, meta):
        return (5 if _grade_resolved(art.get("grade_level")) else 3, "学段解析")

    @staticmethod
    def _safety(art, meta):
        blob = " ".join(str(v) for v in art.values() if isinstance(v, (str, list)))
        return (0 if has_pii(blob) else 5, "PII 检查")

    # ---------------- 汇总 ----------------
    def evaluate(self, artifact: dict, meta: dict | None = None) -> dict:
        meta = meta or {}
        per = []
        total = 0.0
        for c in self.criteria:
            s, note = c.score(artifact, meta)
            total += s * c.weight
            per.append({"key": c.key, "weight": c.weight, "score": s, "note": note})
        return {
            "kind": artifact.get("kind"),
            "overall": round(total, 3),  # 0~5
            "per_criterion": per,
            "passed": total >= 4.0,
        }


def normalize_lesson_plan(resp: dict) -> dict:
    """把接口返回的教案响应归一化为 rubric 可直接打分的 artifact。"""
    text = f"{resp.get('title','')}\n{resp.get('teaching_objectives','')}\n{resp.get('teaching_process','')}"
    kps = resp.get("graph_context") or []
    kp_names = " ".join(str(k.get("name", "")) for k in kps if isinstance(k, dict))
    return {
        "kind": "lesson_plan",
        "title": resp.get("title"),
        "teaching_objectives": resp.get("teaching_objectives"),
        "teaching_process": resp.get("teaching_process"),
        "grade_level": resp.get("grade_level"),
        "references_kp": bool(kp_names),
        "text": text + "\n" + kp_names,
    }


def normalize_summary(resp: dict) -> dict:
    topics = resp.get("key_topics") or []
    text = f"{resp.get('summary','')}\n" + "\n".join(str(t) for t in topics)
    return {
        "kind": "summary",
        "summary": resp.get("summary"),
        "key_topics": topics,
        "grade_level": None,
        "references_kp": False,
        "text": text,
    }


def normalize_chat(resp: dict) -> dict:
    return {
        "kind": "chat_reply",
        "reply": resp.get("reply"),
        "sources": resp.get("sources") or [],
        "grade_level": None,
        "references_kp": False,
        "text": resp.get("reply") or "",
    }
