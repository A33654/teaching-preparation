"""客观题（选择 / 填空）规则判分 —— FR-04。

纯函数、无副作用、可离线运行。归一化覆盖：
- 选择题：选项索引(int) / 数字字符串 / 单字母 A-D（大小写）/ 选项文本完全匹配
- 填空题：去除首尾空白、转小写、剔除中英文标点后与任一标准答案（多解）比对

每个判分结果都带 auto_detail，满足"错判题可溯源"。
"""
from __future__ import annotations

import unicodedata

# 中英文标点与空白，用于填空归一化时剔除
_PUNCT = (
    "，。．、；：？！“”‘’（）《》【】〈〉「」『』"
    "±×÷℃°"
    ",.;:?!\"'()[]{}<>/\\|-_~`@#$%^&*+= \t\n"
)


def _strip_punct(text: str) -> str:
    """去除中英文标点和空白，转小写，用于填空归一化比对。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    return "".join(ch for ch in text if ch not in _PUNCT).strip().lower()


def _parse_choice_index(content, options: list) -> int | None:
    """把学生作答解析成选项索引（int），解析不出返回 None。"""
    if content is None or isinstance(content, bool):
        return None
    if isinstance(content, int):
        return content if 0 <= content < len(options) else None
    if isinstance(content, float):
        idx = int(content)
        return idx if 0 <= idx < len(options) else None
    s = str(content).strip()
    if s == "":
        return None
    # 纯数字字符串
    if s.isdigit():
        idx = int(s)
        return idx if 0 <= idx < len(options) else None
    # 单字母 A-D / a-d（限定 ASCII：中文汉字 isalpha() 也为 True，不能走这条分支）
    if len(s) == 1 and s.isascii() and s.isalpha():
        idx = ord(s.upper()) - ord("A")
        if 0 <= idx < len(options):
            return idx
        # 越界时继续尝试按选项文本匹配
    # 选项文本完全匹配（归一化后）
    norm = _strip_punct(s)
    if norm:
        for i, opt in enumerate(options):
            if _strip_punct(opt) == norm:
                return i
    return None


def grade_choice(question: dict, content) -> dict:
    full = float(question.get("score") or 0.0)
    options = question.get("options") or []
    correct_option = question.get("correct_option")
    student_idx = _parse_choice_index(content, options)
    if student_idx is None:
        return {
            "is_correct": False,
            "auto_score": 0.0,
            "auto_detail": "未识别到有效选项（作答为空或非选项内容），得 0 分",
        }
    if not isinstance(correct_option, int):
        return {
            "is_correct": None,
            "auto_score": None,
            "auto_detail": "题面缺少标准答案（correct_option），无法判分",
        }
    correct_idx = int(correct_option)
    opt_text = lambda i: options[i] if 0 <= i < len(options) else ""
    if student_idx == correct_idx:
        detail = (
            f"学生选 {chr(65 + student_idx)}（{opt_text(student_idx)}），"
            f"标准答案 {chr(65 + correct_idx)}，判定正确，得满分 {full}"
        )
        return {"is_correct": True, "auto_score": full, "auto_detail": detail}
    detail = (
        f"学生选 {chr(65 + student_idx)}（{opt_text(student_idx)}），"
        f"标准答案 {chr(65 + correct_idx)}（{opt_text(correct_idx)}），"
        f"判定错误，得 0 分"
    )
    return {"is_correct": False, "auto_score": 0.0, "auto_detail": detail}


def grade_fill(question: dict, content) -> dict:
    full = float(question.get("score") or 0.0)
    answers = [a for a in (question.get("answers") or []) if a is not None]
    if content is None or str(content).strip() == "":
        return {"is_correct": False, "auto_score": 0.0, "auto_detail": "学生未作答，得 0 分"}
    if not answers:
        return {
            "is_correct": None,
            "auto_score": None,
            "auto_detail": "题面缺少标准答案（多解 answers），无法判分",
        }
    student_norm = _strip_punct(content)
    for ans in answers:
        if _strip_punct(ans) == student_norm:
            detail = (
                f"学生作答「{content}」与标准答案「{ans}」归一化一致，"
                f"判定正确，得满分 {full}"
            )
            return {"is_correct": True, "auto_score": full, "auto_detail": detail}
    accepted = " / ".join(str(a) for a in answers)
    detail = (
        f"学生作答「{content}」与全部标准答案（{accepted}）均不一致，"
        f"判定错误，得 0 分"
    )
    return {"is_correct": False, "auto_score": 0.0, "auto_detail": detail}


def grade_objective(question: dict, content) -> dict:
    """客观题统一入口：choice → 选择判分；fill → 填空判分；其余返回非客观标记。"""
    qtype = question.get("type")
    if qtype == "choice":
        return grade_choice(question, content)
    if qtype == "fill":
        return grade_fill(question, content)
    return {"is_correct": None, "auto_score": None, "auto_detail": "非客观题型"}
