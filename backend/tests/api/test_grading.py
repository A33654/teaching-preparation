"""FR-04/05/06 判分与批改 API 集成测试。

- FR-04：含 10 道选择题的 Submission 触发自动判分，客观题判分正确、可溯源
- FR-05：简答题 AI 给出建议分/评语/置信度，终评字段为空
- FR-06：教师采纳或手动改分 + 终评不可逆（二次确认）
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.models import Homework, HomeworkStatus

TEACHER_EMAIL = "qa_teacher@example.com"
CHOICE_COUNT = 10


def _teacher_id(session: Session) -> uuid.UUID:
    user = crud.get_user_by_email(session=session, email=TEACHER_EMAIL)
    assert user is not None, "教师账号缺失（teacher fixture 未生效）"
    return user.id


def _make_questions() -> list[dict]:
    """10 道选择题 + 1 道简答题（选择题标准答案为 i % 4）。"""
    questions: list[dict] = []
    for i in range(CHOICE_COUNT):
        questions.append(
            {
                "id": f"q{i}",
                "type": "choice",
                "stem": f"选择题{i + 1}",
                "knowledge_point_ids": ["kp-refraction"],
                "options": ["甲", "乙", "丙", "丁"],
                "correct_option": i % 4,
                "answers": [],
                "reference_answer": "",
                "score": 5.0,
            }
        )
    questions.append(
        {
            "id": "short1",
            "type": "short",
            "stem": "简述光的折射现象。",
            "knowledge_point_ids": ["kp-refraction"],
            "options": [],
            "correct_option": None,
            "answers": [],
            "reference_answer": "光从一种介质斜射入另一种介质时传播方向发生改变叫折射。",
            "score": 10.0,
        }
    )
    return questions


def _make_published_homework_and_submission(
    client: TestClient, session: Session, headers: dict[str, str]
) -> tuple[str, str]:
    """造一份已发布作业 + 一份提交；前 7 题答对，后 3 题故意答错。"""
    hw = Homework(
        title=f"判分验收作业-{uuid.uuid4().hex[:6]}",
        owner_id=_teacher_id(session),
        status=HomeworkStatus.DRAFT,
        knowledge_point_ids=["kp-refraction"],
        questions=_make_questions(),
    )
    session.add(hw)
    session.commit()
    session.refresh(hw)

    r = client.post(f"/api/v1/homework/{hw.id}/publish", headers=headers)
    assert r.status_code == 200, r.text

    answers = []
    for i in range(CHOICE_COUNT):
        if i < 7:
            answers.append({"question_id": f"q{i}", "content": i % 4})  # 正确
        else:
            answers.append({"question_id": f"q{i}", "content": (i % 4 + 1) % 4})  # 错误
    answers.append(
        {"question_id": "short1", "content": "光从一种介质进入另一种介质方向改变，这是折射"}
    )

    r = client.post(
        f"/api/v1/homework/{hw.id}/simulate-submit",
        headers=headers,
        json={"student_id": "2026001", "answers": answers},
    )
    assert r.status_code == 200, r.text
    sub_id = r.json()["id"]
    return str(hw.id), str(sub_id)


def _grade(client: TestClient, headers: dict[str, str], hw_id: str, sub_id: str) -> list[dict]:
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grade", headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()["grades"]


# ==================== FR-04：10 道选择题判分正确 ====================

def test_fr04_auto_grade_ten_choice_questions(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, sub_id = _make_published_homework_and_submission(
        client, db, teacher_token_headers
    )
    grades = _grade(client, teacher_token_headers, hw_id, sub_id)
    assert len(grades) == CHOICE_COUNT + 1

    choice_grades = [g for g in grades if g["question_type"] == "choice"]
    assert len(choice_grades) == CHOICE_COUNT

    correct_count = 0
    match_count = 0
    for g in choice_grades:
        idx = int(g["question_id"][1:])
        expected = idx < 7  # 前 7 题答对
        actual = bool(g["is_correct"])
        assert actual == expected, f"{g['question_id']} 判分错误：{g['auto_detail']}"
        # 判分引擎判定结果与标准答案一致（判分正确，而非"学生答对率"）
        match_count += 1
        if actual:
            correct_count += 1
            assert g["auto_score"] == g["full_score"]
        else:
            assert g["auto_score"] == 0.0
        # 每条判分都可溯源
        assert g["auto_detail"], f"{g['question_id']} 缺少判分依据"

    # FR-04：10 道标准答案题判分正确率 10/10 = 100% ≥ 95%
    assert match_count == CHOICE_COUNT
    assert match_count / CHOICE_COUNT >= 0.95
    assert correct_count == 7


# ==================== FR-05：简答题 AI 建议 ====================

def test_fr05_short_answer_has_ai_suggestion_and_empty_final(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, sub_id = _make_published_homework_and_submission(
        client, db, teacher_token_headers
    )
    grades = _grade(client, teacher_token_headers, hw_id, sub_id)

    short = next(g for g in grades if g["question_type"] == "short")
    # AI 建议字段齐全
    assert short["ai_suggested_score"] is not None
    assert short["ai_comment"]
    assert short["ai_confidence"] is not None and 0.0 <= short["ai_confidence"] <= 1.0
    assert short["ai_knowledge_points"] == ["kp-refraction"]
    # 不写终评：终评字段为空且未落库
    assert short["final_score"] is None
    assert short["finalized"] is False
    # needs_human 与置信度 < 0.7 一致
    assert short["needs_human"] == (short["ai_confidence"] < 0.7)


# ==================== FR-06：教师复核与终评 ====================

def test_fr06_adopt_suggestion_then_final_is_irreversible(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, sub_id = _make_published_homework_and_submission(
        client, db, teacher_token_headers
    )
    grades = _grade(client, teacher_token_headers, hw_id, sub_id)
    short = next(g for g in grades if g["question_type"] == "short")
    qid = short["question_id"]

    # 未二次确认 → 拒绝
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=teacher_token_headers,
        json={"adopt_suggestion": True},
    )
    assert r.status_code == 400, r.text

    # 一键采纳建议 + 二次确认 → 终评落库
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=teacher_token_headers,
        json={"adopt_suggestion": True, "confirm": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["final_score"] == short["ai_suggested_score"]
    assert body["finalized"] is True
    assert body["final_comment"]
    assert body["status"] == "finalized"

    # 再次修改 → 不可逆，409
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=teacher_token_headers,
        json={"final_score": 1.0, "confirm": True},
    )
    assert r.status_code == 409, r.text
    assert "不可再修改" in r.json()["detail"]


def test_fr06_manual_score_and_comment_with_second_confirmation(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, sub_id = _make_published_homework_and_submission(
        client, db, teacher_token_headers
    )
    _grade(client, teacher_token_headers, hw_id, sub_id)
    qid = "q9"  # 该题自动判分为 0 分（答错）

    # 超出满分 → 拒绝
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=teacher_token_headers,
        json={"final_score": 999, "final_comment": "溢出", "confirm": True},
    )
    assert r.status_code == 422, r.text

    # 手动给分（教师改分，覆盖自动判分结果）+ 评语
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=teacher_token_headers,
        json={"final_score": 3.0, "final_comment": "步骤分，教师复核后给分", "confirm": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["final_score"] == 3.0
    assert body["final_comment"] == "步骤分，教师复核后给分"
    assert body["finalized"] is True

    # 查询接口回显终评结果
    r = client.get(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades",
        headers=teacher_token_headers,
    )
    assert r.status_code == 200, r.text
    row = next(g for g in r.json()["data"] if g["question_id"] == qid)
    assert row["final_score"] == 3.0
    assert row["finalized"] is True


def test_fr06_adopt_requires_existing_suggestion(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, sub_id = _make_published_homework_and_submission(
        client, db, teacher_token_headers
    )
    _grade(client, teacher_token_headers, hw_id, sub_id)
    # 选择题无 AI 建议 → 采纳失败
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/q0/finalize",
        headers=teacher_token_headers,
        json={"adopt_suggestion": True, "confirm": True},
    )
    assert r.status_code == 422, r.text


def test_fr06_finalized_grade_survives_regrading(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """FR-06 不可逆：重判不得覆盖教师已确认的终评。"""
    hw_id, sub_id = _make_published_homework_and_submission(
        client, db, teacher_token_headers
    )
    _grade(client, teacher_token_headers, hw_id, sub_id)

    qid = "q9"
    client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=teacher_token_headers,
        json={"final_score": 4.0, "final_comment": "步骤分", "confirm": True},
    )

    # 再次触发判分
    grades = _grade(client, teacher_token_headers, hw_id, sub_id)
    row = next(g for g in grades if g["question_id"] == qid)
    assert row["finalized"] is True
    assert row["final_score"] == 4.0
    assert row["final_comment"] == "步骤分"


def test_grading_requires_homework_ownership(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, sub_id = _make_published_homework_and_submission(
        client, db, teacher_token_headers
    )
    # 超管可访问该作业；此处先验证不存在作业返回 404
    unknown = str(uuid.uuid4())
    r = client.post(
        f"/api/v1/grading/homework/{unknown}/submissions/{sub_id}/grade",
        headers=teacher_token_headers,
    )
    assert r.status_code == 404, r.text
    # 提交不属于该作业 → 404
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{unknown}/grade",
        headers=teacher_token_headers,
    )
    assert r.status_code == 404, r.text


# ==================== FR-04：标注集验收接口 ====================

def test_fr04_labeled_set_verification_endpoint(
    client: TestClient, teacher_token_headers: dict[str, str]
) -> None:
    r = client.post("/api/v1/grading/verify-labeled-set", headers=teacher_token_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["accuracy"] >= 0.95
    assert data["passed"] is True
    assert data["total"] >= 300
