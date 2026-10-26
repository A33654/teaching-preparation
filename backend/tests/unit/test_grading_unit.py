"""FR-04 客观题自动判分单元测试：标注集准确率 ≥95%、错判可溯源、归一化覆盖。"""
from __future__ import annotations

from app.grading.ai_grade import ai_grade_subjective
from app.grading.labeled_set import build_labeled_set, run_labeled_set
from app.grading.objective import grade_objective


def test_fr04_labeled_set_accuracy_at_least_95_percent():
    """Given 标注集，When 触发引擎判分，Then 准确率 ≥95%。"""
    report = run_labeled_set()
    assert report["total"] >= 300, "标注集规模过小"
    assert report["accuracy"] >= 0.95, (
        f"客观题判分准确率 {report['accuracy']:.4f} 低于验收线 95%，"
        f"错判样例：{report['misjudged'][:5]}"
    )
    assert report["passed"] is True


def test_fr04_every_judgement_is_traceable():
    """错判题可溯源：每条判分结果都必须带可读的判分依据 auto_detail。"""
    for case in build_labeled_set():
        res = grade_objective(case["question"], case["content"])
        assert res["auto_detail"], f"{case['question']['id']} 缺少判分依据"


def test_fr04_misjudged_records_carry_detail():
    """即便出现错判，也应留下可溯源信息（expected/got/detail）。"""
    report = run_labeled_set()
    for item in report["misjudged"]:
        assert item["question_id"]
        assert item["expected"] is not None
        assert item["got"] is not None
        assert item["detail"]


def test_choice_normalization_index_letter_text():
    q = {
        "id": "c1",
        "type": "choice",
        "options": ["甲", "乙", "丙", "丁"],
        "correct_option": 1,
        "score": 5.0,
    }
    # 多种等价正确作答形态
    for content in (1, "1", "B", "b", "乙"):
        assert grade_objective(q, content)["is_correct"] is True, content
    # 错误作答
    for content in (0, "0", "A", "丙", "", None):
        assert grade_objective(q, content)["is_correct"] is False, content
    # 得分：正确满分、错误 0 分
    assert grade_objective(q, 1)["auto_score"] == 5.0
    assert grade_objective(q, 0)["auto_score"] == 0.0
    # 溯源文本含"标准答案"
    assert "标准答案" in grade_objective(q, 0)["auto_detail"]


def test_fill_normalization_punctuation_and_case():
    q = {"id": "f1", "type": "fill", "answers": ["光的折射", "折射"], "score": 5.0}
    assert grade_objective(q, "折射")["is_correct"] is True
    assert grade_objective(q, " 折射。 ")["is_correct"] is True  # 标点/空格干扰
    assert grade_objective(q, "光的折射")["is_correct"] is True  # 多解之一
    assert grade_objective(q, "反射")["is_correct"] is False
    assert grade_objective(q, "")["is_correct"] is False
    # 英文大小写不敏感
    q2 = {"id": "f2", "type": "fill", "answers": ["Newton", "牛顿"], "score": 5.0}
    assert grade_objective(q2, "newton")["is_correct"] is True


def test_fill_missing_reference_answer_is_ungradable():
    q = {"id": "f3", "type": "fill", "answers": [], "score": 5.0}
    res = grade_objective(q, "任意作答")
    assert res["is_correct"] is None
    assert "缺少标准答案" in res["auto_detail"]


def test_non_objective_question_is_not_graded_by_rules():
    q = {"id": "s1", "type": "short", "score": 10.0}
    res = grade_objective(q, "...")
    assert res["is_correct"] is None
    assert res["auto_detail"] == "非客观题型"


def test_fr05_ai_suggestion_shape_and_confidence_rule():
    """FR-05：AI 输出建议分/评语/命中知识点/置信度；<0.7 强制"建议人工"。"""
    q = {
        "id": "s1",
        "type": "short",
        "stem": "简述光的折射现象。",
        "reference_answer": "光从一种介质斜射入另一种介质时，传播方向发生改变，这种现象叫做光的折射。",
        "knowledge_point_ids": ["kp-refraction"],
        "score": 10.0,
    }
    res = ai_grade_subjective(q, "光从一种介质进入另一种介质，方向发生改变，这叫折射")
    assert 0.0 <= res["ai_suggested_score"] <= 10.0
    assert isinstance(res["ai_comment"], str) and res["ai_comment"]
    assert res["ai_knowledge_points"] == ["kp-refraction"]
    assert 0.0 <= res["ai_confidence"] <= 1.0
    # needs_human 严格等价于"置信度 < 0.7"
    assert res["needs_human"] == (res["ai_confidence"] < 0.7)


def test_fr05_empty_answer_forces_human_review():
    q = {
        "id": "s2",
        "type": "short",
        "stem": "简述……",
        "reference_answer": "参考答案要点",
        "knowledge_point_ids": ["kp-1"],
        "score": 10.0,
    }
    res = ai_grade_subjective(q, "")
    assert res["ai_confidence"] < 0.7
    assert res["needs_human"] is True
    assert res["ai_suggested_score"] == 0.0
