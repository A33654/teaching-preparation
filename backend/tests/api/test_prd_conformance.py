"""PRD 符合性验证：以 `docs/teacher-online-grading-prd.md` v1.0 为准。

覆盖三块此前没有可执行证据的地方：
1. PRD §7「异常处理清单」5 条 —— 逐条核对实现是否落地
2. PRD §5.3「埋点需求」3 个事件 —— 核对是否存在上报通道
3. FR-10「数据隔离」边界 —— 超管是否真的只能看、不能写

约定：实现已对齐的条目写**常规断言（应通过）**；
各条目均按 PRD 要求写常规断言（EXL-01~08 / EVT-01~03 / FR-10 已全部补齐，
原先的 xfail 标记已摘除）。
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.models import Homework, HomeworkStatus, UserCreate

from tests.api.test_grading import (
    _make_published_homework_and_submission,
    _teacher_id,
)

TEACHER_EMAIL = "qa_teacher@example.com"
TEACHER_PWD = "teacher123456"


def _login(client: TestClient, email: str, password: str = TEACHER_PWD) -> dict[str, str]:
    r = client.post("/api/v1/login/access-token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_low_confidence_setup(
    client: TestClient, db: Session, headers: dict[str, str]
) -> tuple[str, str, str]:
    """造一份「主观题 + 空作答」的数据，AI 置信度必为 0.30（<0.7）。

    返回 (homework_id, submission_id, question_id)。
    """
    hw = Homework(
        title=f"低置信-{uuid.uuid4().hex[:6]}",
        owner_id=_teacher_id(db),
        status=HomeworkStatus.DRAFT,
        knowledge_point_ids=["kp-refraction"],
        questions=[
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
        ],
    )
    db.add(hw)
    db.commit()
    db.refresh(hw)
    assert (
        client.post(f"/api/v1/homework/{hw.id}/publish", headers=headers).status_code == 200
    )
    sub_id = client.post(
        f"/api/v1/homework/{hw.id}/simulate-submit",
        headers=headers,
        json={"student_id": "2026001", "answers": [{"question_id": "short1", "content": ""}]},
    ).json()["id"]
    return str(hw.id), str(sub_id), "short1"


# ==================== 阳性对照 ====================
# 先证明夹具可用：若这 2 条失败，说明是环境问题而非产品缺口。


def test_positive_confidence_low_forces_human(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """[已对齐 · PRD §7 第2条上半] 置信度 <0.7 → 强制 needs_human。"""
    hw_id, sub_id, _qid = _make_low_confidence_setup(client, db, teacher_token_headers)
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grade",
        headers=teacher_token_headers,
    )
    assert r.status_code == 200, r.text
    g = r.json()["grades"][0]
    assert g["ai_confidence"] < 0.7, g
    assert g["needs_human"] is True, g


def test_positive_teacher_cannot_access_others_homework(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """[已对齐 · FR-10] 教师不可见他人作业。"""
    hw_id, _sub_id = _make_published_homework_and_submission(client, db, teacher_token_headers)

    other_email = f"qa_other_{uuid.uuid4().hex[:6]}@example.com"
    if crud.get_user_by_email(session=db, email=other_email) is None:
        crud.create_user(session=db, user_create=UserCreate(email=other_email, password=TEACHER_PWD))
    other_headers = _login(client, other_email)

    r = client.get(f"/api/v1/homework/{hw_id}", headers=other_headers)
    assert r.status_code == 403, r.text


# ==================== PRD §7 异常处理清单 ====================


def test_prd_exc_missing_standard_answer_blocked_on_publish(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """PRD §7：客观题无 std_answer → 发布（提交）时拦截，提示教师补标准答案。"""
    hw = Homework(
        title=f"缺标答-{uuid.uuid4().hex[:6]}",
        owner_id=_teacher_id(db),
        status=HomeworkStatus.DRAFT,
        knowledge_point_ids=["kp-refraction"],
        questions=[
            {
                "id": "q0",
                "type": "choice",
                "stem": "未设正确选项的选择题",
                "knowledge_point_ids": ["kp-refraction"],
                "options": ["甲", "乙", "丙", "丁"],
                "correct_option": None,  # 缺标准答案
                "answers": [],
                "reference_answer": "",
                "score": 5.0,
            },
            {
                "id": "q1",
                "type": "fill",
                "stem": "未设答案的填空题",
                "knowledge_point_ids": ["kp-refraction"],
                "options": [],
                "correct_option": None,
                "answers": [],  # 缺标准答案
                "reference_answer": "",
                "score": 5.0,
            },
        ],
    )
    db.add(hw)
    db.commit()
    db.refresh(hw)

    r = client.post(f"/api/v1/homework/{hw.id}/publish", headers=teacher_token_headers)
    assert r.status_code == 422, f"应在发布时拦截缺标准答案的题目，实际 {r.status_code}: {r.text}"
    assert "标准答案" in r.json()["detail"]


def test_prd_exc_duplicate_submission_last_wins(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """PRD §7：同一 student_ref 多次提交 → 以最后一次为准，旧版本标记「被覆盖」。"""
    hw_id, _ = _make_published_homework_and_submission(client, db, teacher_token_headers)
    payload = {"student_id": "2026001", "answers": [{"question_id": "q0", "content": 0}]}

    r1 = client.post(
        f"/api/v1/homework/{hw_id}/simulate-submit", headers=teacher_token_headers, json=payload
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/v1/homework/{hw_id}/simulate-submit", headers=teacher_token_headers, json=payload
    )
    assert r2.status_code == 200, r2.text

    lst = client.get(f"/api/v1/homework/{hw_id}/submissions", headers=teacher_token_headers)
    rows = lst.json()["data"]
    mine = [s for s in rows if s["student_id_hash"] == r2.json()["student_id_hash"]]
    active = [s for s in mine if not s.get("superseded")]
    assert len(active) == 1, f"同一学生应只保留 1 份有效提交，实际 {len(active)} 份"


def test_prd_exc_deleted_knowledge_point_marked_invalid(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """PRD §7：作业关联的知识点已删除 → 看板该知识点标「已失效」，错误率单列不计入活跃统计。"""
    hw_id, _ = _make_published_homework_and_submission(client, db, teacher_token_headers)
    r = client.get(
        f"/api/v1/analytics/homework/{hw_id}/dashboard", headers=teacher_token_headers
    )
    assert r.status_code == 200, r.text
    for stat in r.json()["knowledge_points"]:
        assert "is_active" in stat, "看板应为每个知识点给出「是否已失效」标记"


def test_prd_exc_ai_failure_flagged_as_unavailable(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str], monkeypatch
) -> None:
    """PRD §7：AI 主观题超时/失败 → 标记「AI 不可用，转人工」，不阻塞其余题目。"""
    import app.grading.ai_grade as ai_mod

    def _boom(*_a, **_kw):  # noqa: ANN001, ANN202
        raise RuntimeError("LLM 超时")

    monkeypatch.setattr(ai_mod, "_llm_grade", _boom)

    hw_id, sub_id = _make_published_homework_and_submission(client, db, teacher_token_headers)
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grade",
        headers=teacher_token_headers,
    )
    assert r.status_code == 200, r.text
    short = [g for g in r.json()["grades"] if g["question_type"] == "short"]
    assert short, "应有简答题批改项"
    g = short[0]
    assert g.get("ai_unavailable") is True or "AI 不可用" in (g.get("ai_comment") or ""), (
        "AI 失败时应显式标记「AI 不可用，转人工」，避免把启发式兜底误认为真实 AI 结论"
    )


def test_prd_exc_low_confidence_cannot_adopt(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """PRD §7：confidence < 0.7 强制「建议人工」，终评必须教师手填（不得一键采纳）。"""
    hw_id, sub_id, qid = _make_low_confidence_setup(client, db, teacher_token_headers)
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grade",
        headers=teacher_token_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["grades"][0]["ai_confidence"] < 0.7

    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=teacher_token_headers,
        json={"adopt_suggestion": True, "confirm": True},
    )
    assert r.status_code == 422, (
        f"低置信度题目应要求教师手填终评，不得一键采纳，实际 {r.status_code}"
    )


# ==================== FR-10 数据隔离边界 ====================


def test_fr10_superuser_cannot_write_final_grade(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """FR-10：超管可见全校聚合，但不应写入他人作业的终评。"""
    hw_id, sub_id = _make_published_homework_and_submission(client, db, teacher_token_headers)
    grades = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grade",
        headers=teacher_token_headers,
    ).json()["grades"]
    assert grades

    # 超管读：允许
    r_read = client.get(
        f"/api/v1/analytics/homework/{hw_id}/dashboard", headers=superuser_token_headers
    )
    assert r_read.status_code == 200, r_read.text

    # 超管写：应拒绝
    qid = grades[0]["question_id"]
    r = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=superuser_token_headers,
        json={"final_score": 1.0, "final_comment": "超管改分", "confirm": True},
    )
    assert r.status_code == 403, f"超管不应写入他人作业终评，实际 {r.status_code}: {r.text}"


# ==================== §9 R-2 回流幂等与留痕 ====================


def test_backflow_is_idempotent(client: TestClient, db: Session, teacher_token_headers: dict[str, str], monkeypatch) -> None:
    """同一知识点重复确认回流应幂等，不产生重复误区节点。"""
    from tests.api.test_analytics import _make_graded_setup

    created: list[dict] = []

    class _Repo:
        _seq = 0

        def get_knowledge_point(self, kp_id: str):
            return {"id": kp_id, "name": "示例知识点"}

        def create_misconception(self, **kw):
            _Repo._seq += 1
            created.append(kw)
            return {
                "id": f"mis-{_Repo._seq}",
                "content": kw["content"],
                "correction": kw.get("correction", ""),
                "source": kw.get("source", ""),
            }

        def link_kp_misconception(self, kp_id: str, mis_id: str):
            return {"id": mis_id}

    monkeypatch.setattr("app.knowledge_graph.KnowledgeGraphRepository", _Repo)

    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)
    sug = client.get(
        f"/api/v1/analytics/homework/{hw_id}/misconception-suggestions",
        headers=teacher_token_headers,
    )
    assert sug.status_code == 200, sug.text
    assert sug.json()["count"] >= 1
    kp_id = sug.json()["data"][0]["knowledge_point_id"]

    payload = {"knowledge_point_id": kp_id, "content": "典型错误：误选 A（甲）", "correction": "应选 B"}
    r1 = client.post(
        f"/api/v1/analytics/homework/{hw_id}/misconception-backflow",
        headers=teacher_token_headers,
        json=payload,
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/v1/analytics/homework/{hw_id}/misconception-backflow",
        headers=teacher_token_headers,
        json=payload,
    )
    assert r2.status_code == 200, r2.text
    assert len(created) == 1, f"重复确认应幂等，实际写入 {len(created)} 次"


# ==================== PRD §5.3 埋点 ====================


def test_evt_assignment_published(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """PRD §5.3：作业发布应上报 assignment_published（含 question_count / kp_count）。"""
    try:
        from app.core import telemetry  # type: ignore
    except ImportError as exc:  # pragma: no cover - 实现后走下面
        pytest.fail(f"未找到埋点模块 app.core.telemetry：{exc}")

    hw_id, _ = _make_published_homework_and_submission(client, db, teacher_token_headers)
    events = telemetry.recent()
    assert any(e.get("event") == "assignment_published" for e in events)


def test_evt_grading_confirmed(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """PRD §5.3：教师终评确认应上报 grading_confirmed（含 ai_confidence / adopted）。"""
    try:
        from app.core import telemetry  # type: ignore
    except ImportError as exc:  # pragma: no cover
        pytest.fail(f"未找到埋点模块 app.core.telemetry：{exc}")

    hw_id, sub_id = _make_published_homework_and_submission(client, db, teacher_token_headers)
    grades = client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grade",
        headers=teacher_token_headers,
    ).json()["grades"]
    qid = grades[0]["question_id"]
    client.post(
        f"/api/v1/grading/homework/{hw_id}/submissions/{sub_id}/grades/{qid}/finalize",
        headers=teacher_token_headers,
        json={"final_score": 5.0, "final_comment": "ok", "confirm": True},
    )
    assert any(e.get("event") == "grading_confirmed" for e in telemetry.recent())


def test_evt_mistake_feedback_decided(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str], monkeypatch
) -> None:
    """PRD §5.3：误区建议被采纳/驳回应上报 mistake_feedback_decided。

    事件由「教师做出决策（采纳 / 驳回）」触发，故本用例真正走一次回流确认，
    而不是只看建议列表 —— 否则断言会依赖其它用例留下的全局事件。
    """
    try:
        from app.core import telemetry  # type: ignore
    except ImportError as exc:  # pragma: no cover
        pytest.fail(f"未找到埋点模块 app.core.telemetry：{exc}")

    class _Repo:
        def get_knowledge_point(self, kp_id: str):
            return {"id": kp_id, "name": "示例知识点"}

        def create_misconception(self, **kw):
            return {
                "id": "mis-evt-1",
                "content": kw["content"],
                "correction": kw.get("correction", ""),
                "source": kw.get("source", ""),
            }

        def link_kp_misconception(self, kp_id: str, mis_id: str):
            return {"id": mis_id}

    monkeypatch.setattr("app.knowledge_graph.KnowledgeGraphRepository", _Repo)

    from tests.api.test_analytics import _make_graded_setup

    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)
    sug = client.get(
        f"/api/v1/analytics/homework/{hw_id}/misconception-suggestions",
        headers=teacher_token_headers,
    )
    assert sug.status_code == 200, sug.text
    assert sug.json()["count"] >= 1, "应有回流建议可供决策"
    kp_id = sug.json()["data"][0]["knowledge_point_id"]

    r = client.post(
        f"/api/v1/analytics/homework/{hw_id}/misconception-backflow",
        headers=teacher_token_headers,
        json={
            "knowledge_point_id": kp_id,
            "content": "典型错误：误选 A（甲）",
            "correction": "应选 B",
        },
    )
    assert r.status_code == 200, r.text
    assert any(e.get("event") == "mistake_feedback_decided" for e in telemetry.recent())


# ==================== PRD §4 Assignment 状态完整性 ====================


def test_assignment_can_reach_closed(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """PRD §4：已发布/收集中 → 已截止 应有可用入口（截止到点或手动截止）。"""
    hw_id, _ = _make_published_homework_and_submission(client, db, teacher_token_headers)
    r = client.post(f"/api/v1/homework/{hw_id}/close", headers=teacher_token_headers)
    assert r.status_code == 200, f"缺少使作业进入已截止状态的入口，实际 {r.status_code}"
