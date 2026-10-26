# -*- coding: utf-8 -*-
"""L3 AI 评测：对真实接口产出的 AI 内容做规则化 rubric 评分。

产物来源（接口，离线 LLM 桩驱动）：
  - 教案：POST /lesson-plans/ai-generate
  - 概括：POST /lesson-plans/summarize
  - 问答：POST /chat （json 模式）

合格线：每个产物 overall >= 4.0 / 5.0。结果写入 tests/ai_eval/results/ai_eval.json 供平台汇总。
"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from tests.ai_eval.rubric import (
    AIRubric,
    normalize_chat,
    normalize_lesson_plan,
    normalize_summary,
)

API = "/api/v1"
RESULTS = Path(__file__).parent / "results" / "ai_eval.json"


def test_ai_eval_runs_and_meets_threshold(client, teacher_token_headers, superuser_token_headers):
    rubric = AIRubric()
    results = []

    # 1) 教案生成（带章节，命中知识库 -> 期望引用知识点）
    lp = client.post(
        f"{API}/lesson-plans/ai-generate", headers=teacher_token_headers,
        json={"subject": "数学", "grade_level": "高中", "chapter": "函数与导数"},
    )
    assert lp.status_code == 200, lp.text
    lp_art = normalize_lesson_plan(lp.json())
    lp_res = rubric.evaluate(lp_art, meta={"kb_expected": True})
    results.append({"case": "lesson_plan_ai_generate", **lp_res})

    # 2) 文档概括
    files = {"file": ("素材.txt", BytesIO("二次函数是形如 y=ax^2+bx+c 的函数，图像为抛物线。".encode("utf-8") * 10), "text/plain")}
    sm = client.post(f"{API}/lesson-plans/summarize", headers=teacher_token_headers, files=files)
    assert sm.status_code == 200, sm.text
    sm_art = normalize_summary(sm.json())
    sm_res = rubric.evaluate(sm_art, meta={})
    results.append({"case": "document_summarize", **sm_res})

    # 3) 教学问答（json 模式，LLM 桩）
    ch = client.post(
        f"{API}/chat/", headers=teacher_token_headers,
        json={"message": "请讲解二次函数的基本性质", "mode": "json"},
    )
    assert ch.status_code == 200, ch.text
    ch_art = normalize_chat(ch.json())
    ch_res = rubric.evaluate(ch_art, meta={})
    results.append({"case": "chat_qa", **ch_res})

    # 合格判定
    overall_scores = [r["overall"] for r in results]
    min_score = min(overall_scores)
    passed_all = all(r["passed"] for r in results)

    report = {
        "rubric_weights": {c.key: c.weight for c in rubric.criteria},
        "threshold": 4.0,
        "cases": results,
        "min_score": min_score,
        "average_score": round(sum(overall_scores) / len(overall_scores), 3),
        "all_passed": passed_all,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 断言：所有产物达到合格线
    assert passed_all, f"AI 评测未达标：{report}"
    # 同时校验可解析性与非错误产物
    assert lp_art["references_kp"] is True, "教案应引用知识点（知识库可追溯）"
