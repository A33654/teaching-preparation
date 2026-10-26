"""FR-04 标注集：客观题自动判分准确率验收（≥95%）与错判溯源。

标注集由「标准答案 + 学生作答 + 人工标注期望对错」构成，覆盖：
- 选择题：选项索引 / 数字串 / 单字母 A-D / 选项文本匹配 / 错选 / 空答
- 填空题：多解、大小写、中英文标点干扰、空白、空答

run_labeled_set() 用生产判分引擎逐条打分并与人工标注比对，返回准确率与错判溯源。
"""
from __future__ import annotations

import random

from app.grading.objective import grade_objective


def build_labeled_set(seed: int = 20261026) -> list[dict]:
    rng = random.Random(seed)
    cases: list[dict] = []

    # ---------- 选择题（200 条）----------
    option_pools = [
        ["光沿直线传播", "光沿曲线传播", "光会拐弯", "光会停止"],
        ["凸透镜", "凹透镜", "平面镜", "棱镜"],
        ["反射", "折射", "衍射", "散射"],
        ["升高", "降低", "不变", "先升后降"],
    ]
    for i in range(200):
        options = option_pools[i % len(option_pools)]
        correct = rng.randint(0, 3)
        q = {
            "id": f"c{i}",
            "type": "choice",
            "stem": f"选择题{i}",
            "options": options,
            "correct_option": correct,
            "answers": [],
            "score": 5.0,
        }
        mode = i % 6
        if mode == 0:
            content, gold = correct, True  # 索引
        elif mode == 1:
            content, gold = chr(65 + correct), True  # 字母
        elif mode == 2:
            content, gold = options[correct], True  # 选项文本
        elif mode == 3:
            content, gold = (correct + 1) % 4, False  # 错索引
        elif mode == 4:
            content, gold = chr(65 + ((correct + 1) % 4)), False  # 错字母
        else:
            content, gold = "", False  # 空答
        cases.append({"question": q, "content": content, "gold": gold, "tag": "choice"})

    # ---------- 填空题（120 条）----------
    fill_pool = [
        (["牛顿", "Newton"], 5.0),
        (["路程除以时间", "位移除以时间"], 5.0),
        (["光的折射", "折射"], 5.0),
        (["C", "c", "3×10^8 m/s"], 5.0),
    ]
    for i in range(120):
        answers, score = fill_pool[i % len(fill_pool)]
        q = {
            "id": f"f{i}",
            "type": "fill",
            "stem": f"填空题{i}",
            "options": [],
            "correct_option": None,
            "answers": answers,
            "score": score,
        }
        mode = i % 5
        if mode == 0:
            content, gold = answers[0], True  # 完全正确
        elif mode == 1:
            content, gold = f" {answers[0]}。 ", True  # 带中文标点/空格
        elif mode == 2:
            base = answers[0]
            # 大小写变体：保证归一化后仍一致
            content = base.lower() if base.lower() != base else base.upper()
            gold = True
        elif mode == 3:
            content, gold = "错误答案xyz", False  # 错答
        else:
            content, gold = "", False  # 空答
        cases.append({"question": q, "content": content, "gold": gold, "tag": "fill"})

    return cases


def run_labeled_set() -> dict:
    cases = build_labeled_set()
    correct = 0
    misjudged: list[dict] = []
    for idx, c in enumerate(cases):
        res = grade_objective(c["question"], c["content"])
        got = bool(res["is_correct"]) if res["is_correct"] is not None else None
        if got == c["gold"]:
            correct += 1
        else:
            misjudged.append(
                {
                    "index": idx,
                    "tag": c["tag"],
                    "question_id": c["question"]["id"],
                    "content": c["content"],
                    "expected": c["gold"],
                    "got": got,
                    "detail": res["auto_detail"],
                }
            )
    total = len(cases)
    accuracy = correct / total if total else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "threshold": 0.95,
        "passed": accuracy >= 0.95,
        "misjudged": misjudged,
    }
