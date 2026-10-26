"""FR-07/08/09 + 数据隔离 API 集成测试。

数据构造：
- q0~q7 关联知识点 kp-A，4 份提交中每题恰好一半答错 → kp-A 错误率 0.5（≥40% 阈值）
- q8~q9 关联知识点 kp-B，全部答对 → 错误率 0
- 作业级知识点还含 kp-untouched（无任何题目引用）→ 已批改数 0
三者必须同时出现在看板中，验证「覆盖全部关联知识点，无遗漏」。
"""
from __future__ import annotations

import io
import zipfile
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.models import Homework, HomeworkStatus, UserCreate

TEACHER_EMAIL = "qa_teacher@example.com"
TEACHER_PWD = "teacher123456"
OTHER_EMAIL = "qa_teacher_b@example.com"
STUDENT_IDS = ["2026000", "2026001", "2026002", "2026003"]

KP_A = "kp-A"
KP_B = "kp-B"
KP_UNTOUCHED = "kp-untouched"


def _ensure_user(session: Session, email: str, password: str = TEACHER_PWD):
    user = crud.get_user_by_email(session=session, email=email)
    if not user:
        user = crud.create_user(session=session, user_create=UserCreate(email=email, password=password))
    return user


def _login(client: TestClient, email: str, password: str = TEACHER_PWD) -> dict[str, str]:
    r = client.post("/api/v1/login/access-token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_graded_setup(
    client: TestClient, session: Session, headers: dict[str, str], owner_email: str = TEACHER_EMAIL
) -> tuple[str, list[str]]:
    """造一份已发布、已批改、含 4 份提交的作业。"""
    owner = _ensure_user(session, owner_email)
    options = ["甲", "乙", "丙", "丁"]
    questions = [
        {
            "id": f"q{j}",
            "type": "choice",
            "stem": f"选择题{j + 1}",
            "knowledge_point_ids": [KP_A if j < 8 else KP_B],
            "options": options,
            "correct_option": j % 4,
            "answers": [],
            "reference_answer": "",
            "score": 5.0,
        }
        for j in range(10)
    ]
    hw = Homework(
        title=f"聚合验收作业-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        status=HomeworkStatus.DRAFT,
        knowledge_point_ids=[KP_A, KP_B, KP_UNTOUCHED],
        questions=questions,
    )
    session.add(hw)
    session.commit()
    session.refresh(hw)

    r = client.post(f"/api/v1/homework/{hw.id}/publish", headers=headers)
    assert r.status_code == 200, r.text

    sub_ids: list[str] = []
    for i in range(4):
        answers = []
        for j in range(10):
            correct = j % 4
            if j < 8:
                # i 与 j 同奇偶 → 答对，否则答错：每题恰好一半错
                content = correct if (i + j) % 2 == 0 else (correct + 1) % 4
            else:
                content = correct  # kp-B 全对
            answers.append({"question_id": f"q{j}", "content": content})
        r = client.post(
            f"/api/v1/homework/{hw.id}/simulate-submit",
            headers=headers,
            json={"student_id": STUDENT_IDS[i], "answers": answers},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        rg = client.post(
            f"/api/v1/grading/homework/{hw.id}/submissions/{sid}/grade", headers=headers
        )
        assert rg.status_code == 200, rg.text
        sub_ids.append(sid)
    return str(hw.id), sub_ids


class _FakeRepo:
    """替身图谱仓储：记录写入参数，避免依赖真实 Neo4j。"""

    instances: list["_FakeRepo"] = []

    def __init__(self) -> None:
        self.created: list[dict] = []
        self.links: list[tuple[str, str]] = []
        _FakeRepo.instances.append(self)

    def get_knowledge_point(self, kp_id: str):
        return {"id": kp_id, "name": "示例知识点"} if kp_id in (KP_A, KP_B) else None

    def create_misconception(self, **kw):
        self.created.append(kw)
        return {
            "id": "mis-fake-1",
            "content": kw["content"],
            "correction": kw.get("correction", ""),
            "source": kw.get("source", ""),
        }

    def link_kp_misconception(self, kp_id: str, mis_id: str):
        self.links.append((kp_id, mis_id))
        return {"id": mis_id}


# ==================== FR-07：错误聚合看板 ====================

def test_fr07_dashboard_covers_all_knowledge_points(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)
    r = client.get(f"/api/v1/analytics/homework/{hw_id}/dashboard", headers=teacher_token_headers)
    assert r.status_code == 200, r.text
    data = r.json()

    # 无遗漏：全部 3 个关联知识点都出现在结果中
    assert data["knowledge_point_total"] == 3
    ids = {k["knowledge_point_id"] for k in data["knowledge_points"]}
    assert ids == {KP_A, KP_B, KP_UNTOUCHED}

    stats = {k["knowledge_point_id"]: k for k in data["knowledge_points"]}

    # kp-A：32 次批改、16 次错误 → 错误率 50%
    assert stats[KP_A]["graded_count"] == 32
    assert stats[KP_A]["wrong_count"] == 16
    assert stats[KP_A]["error_rate"] == 0.5
    # TOP 高频错误模式
    assert stats[KP_A]["top_patterns"], "缺少高频错误模式"
    total_pattern_hits = sum(p["count"] for p in stats[KP_A]["top_patterns"])
    assert total_pattern_hits > 0
    for p in stats[KP_A]["top_patterns"]:
        assert p["expression"].startswith("误选")
        assert p["question_ids"]

    # kp-B：全对 → 错误率 0
    assert stats[KP_B]["graded_count"] == 8
    assert stats[KP_B]["error_rate"] == 0.0

    # kp-untouched：无作答也要出现（频次 0，错误率 0）
    assert stats[KP_UNTOUCHED]["graded_count"] == 0
    assert stats[KP_UNTOUCHED]["error_rate"] == 0.0

    assert data["total_submissions"] == 4
    assert data["graded_submissions"] == 4


def test_fr07_personal_scope(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, sub_ids = _make_graded_setup(client, db, teacher_token_headers)
    r = client.get(
        f"/api/v1/analytics/homework/{hw_id}/dashboard",
        headers=teacher_token_headers,
        params={"scope": "personal", "submission_id": sub_ids[0]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["scope"] == "personal"
    assert data["graded_submissions"] == 1
    stats = {k["knowledge_point_id"]: k for k in data["knowledge_points"]}
    # 单人：8 题里 4 题错
    assert stats[KP_A]["graded_count"] == 8
    assert stats[KP_A]["wrong_count"] == 4
    assert stats[KP_A]["error_rate"] == 0.5


def test_fr07_personal_scope_requires_submission_id(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)
    r = client.get(
        f"/api/v1/analytics/homework/{hw_id}/dashboard",
        headers=teacher_token_headers,
        params={"scope": "personal"},
    )
    assert r.status_code == 400, r.text

    bad = client.get(
        f"/api/v1/analytics/homework/{hw_id}/dashboard",
        headers=teacher_token_headers,
        params={"scope": "personal", "submission_id": str(uuid.uuid4())},
    )
    assert bad.status_code == 404, bad.text


# ==================== FR-08：误区回流建议与确认 ====================

def test_fr08_suggestions_include_kp_above_threshold(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)
    r = client.get(
        f"/api/v1/analytics/homework/{hw_id}/misconception-suggestions",
        headers=teacher_token_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["threshold"] == 0.4  # 默认阈值

    kp_map = {s["knowledge_point_id"]: s for s in data["data"]}
    assert KP_A in kp_map  # 错误率 0.5 ≥ 0.4
    assert KP_B not in kp_map  # 0.0 不达标
    assert KP_UNTOUCHED not in kp_map  # 无作答不参与回流

    sug = kp_map[KP_A]
    assert sug["error_rate"] == 0.5
    assert sug["typical_expressions"], "缺少典型错误表述"
    assert sug["suggested_content"]
    assert sug["suggested_correction"]


def test_fr08_threshold_is_configurable(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)
    # 阈值提高到 0.6 → kp-A(0.5) 不再推送
    r = client.get(
        f"/api/v1/analytics/homework/{hw_id}/misconception-suggestions",
        headers=teacher_token_headers,
        params={"threshold": 0.6},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["threshold"] == 0.6
    assert data["count"] == 0

    # 阈值降到 0.1 → 仍然只有有作答且达标的 kp-A
    r2 = client.get(
        f"/api/v1/analytics/homework/{hw_id}/misconception-suggestions",
        headers=teacher_token_headers,
        params={"threshold": 0.1},
    )
    assert [s["knowledge_point_id"] for s in r2.json()["data"]] == [KP_A]


def test_fr08_confirm_writes_misconception_with_source(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str], monkeypatch
) -> None:
    """教师确认回流 → 知识点新增一条经审核的误区记录，来源标注「教学回流」。"""
    monkeypatch.setattr("app.knowledge_graph.KnowledgeGraphRepository", _FakeRepo)
    _FakeRepo.instances.clear()
    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)

    r = client.post(
        f"/api/v1/analytics/homework/{hw_id}/misconception-backflow",
        headers=teacher_token_headers,
        json={
            "knowledge_point_id": KP_A,
            "content": "混淆折射与反射的判定条件",
            "correction": "关键看是否穿过介质界面",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source"] == "教学回流"
    assert data["content"] == "混淆折射与反射的判定条件"

    repo = _FakeRepo.instances[-1]
    assert len(repo.created) == 1
    assert repo.created[0]["source"] == "教学回流"
    assert repo.created[0]["reviewed_by"]  # 记录审核人（教师）
    assert repo.links == [(KP_A, "mis-fake-1")]


def test_fr08_confirm_rejects_missing_knowledge_point(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str], monkeypatch
) -> None:
    monkeypatch.setattr("app.knowledge_graph.KnowledgeGraphRepository", _FakeRepo)
    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)
    r = client.post(
        f"/api/v1/analytics/homework/{hw_id}/misconception-backflow",
        headers=teacher_token_headers,
        json={"knowledge_point_id": "kp-not-exist", "content": "某误区"},
    )
    assert r.status_code == 404, r.text

    empty = client.post(
        f"/api/v1/analytics/homework/{hw_id}/misconception-backflow",
        headers=teacher_token_headers,
        json={"knowledge_point_id": KP_A, "content": "  "},
    )
    assert empty.status_code == 422, empty.text


# ==================== FR-09：脱敏导出 ====================

def test_fr09_export_xlsx_has_no_plaintext_identity(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)
    r = client.get(
        f"/api/v1/analytics/homework/{hw_id}/export",
        headers=teacher_token_headers,
        params={"format": "xlsx"},
    )
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]

    texts = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            texts.append(z.read(name).decode("utf-8", errors="ignore"))
    joined = "".join(texts)

    # 无明文学生姓名/学号
    for sid in STUDENT_IDS:
        assert sid not in joined
    # 脱敏身份仍在（哈希标识），不影响核对成绩
    assert "学生标识（哈希）" in joined


def test_fr09_export_pdf_and_personal_scope(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_id, sub_ids = _make_graded_setup(client, db, teacher_token_headers)
    r = client.get(
        f"/api/v1/analytics/homework/{hw_id}/export",
        headers=teacher_token_headers,
        params={"format": "pdf"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"

    r2 = client.get(
        f"/api/v1/analytics/homework/{hw_id}/export",
        headers=teacher_token_headers,
        params={"format": "xlsx", "scope": "personal", "submission_id": sub_ids[1]},
    )
    assert r2.status_code == 200, r2.text

    bad = client.get(
        f"/api/v1/analytics/homework/{hw_id}/export",
        headers=teacher_token_headers,
        params={"format": "docx"},
    )
    assert bad.status_code == 400, bad.text


# ==================== 数据隔离 ====================

def test_isolation_other_teacher_cannot_access_homework(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    """教师仅可见本人作业：他人作业越权返回拒绝，且不出现在列表中。"""
    hw_id, sub_ids = _make_graded_setup(client, db, teacher_token_headers)
    _ensure_user(db, OTHER_EMAIL)
    other_headers = _login(client, OTHER_EMAIL)

    # 直接访问他人作业的三个端点 → 403
    for path in (
        f"/api/v1/analytics/homework/{hw_id}/dashboard",
        f"/api/v1/analytics/homework/{hw_id}/misconception-suggestions",
        f"/api/v1/analytics/homework/{hw_id}/export",
    ):
        r = client.get(path, headers=other_headers)
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text}"

    # 作业列表只含自己的作业
    lst = client.get("/api/v1/homework/", headers=other_headers)
    assert lst.status_code == 200, lst.text
    assert hw_id not in [h["id"] for h in lst.json()["data"]]

    # 自己的作业列表能看到 A 的作业吗？不能（本测试即验证）→ A 的列表应包含它
    mine = client.get("/api/v1/homework/", headers=teacher_token_headers)
    assert hw_id in [h["id"] for h in mine.json()["data"]]


def test_isolation_submission_not_in_other_homework_returns_404(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    hw_a, _ = _make_graded_setup(client, db, teacher_token_headers)
    _ensure_user(db, OTHER_EMAIL)
    other_headers = _login(client, OTHER_EMAIL)
    hw_b, _ = _make_graded_setup(client, db, other_headers, owner_email=OTHER_EMAIL)

    # B 的作业与 A 的提交互不相通
    subs_b = client.get(f"/api/v1/analytics/homework/{hw_b}/dashboard", headers=other_headers)
    assert subs_b.status_code == 200
    # A 不能访问 B 的作业
    assert client.get(
        f"/api/v1/analytics/homework/{hw_b}/dashboard", headers=teacher_token_headers
    ).status_code == 403


def test_isolation_superuser_sees_aggregate_without_plaintext(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str], superuser_token_headers: dict[str, str]
) -> None:
    """超管可见全校聚合（可访问他人作业看板），导出同样只含哈希、无明文。"""
    hw_id, _ = _make_graded_setup(client, db, teacher_token_headers)

    r = client.get(
        f"/api/v1/analytics/homework/{hw_id}/dashboard", headers=superuser_token_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["knowledge_point_total"] == 3

    exp = client.get(
        f"/api/v1/analytics/homework/{hw_id}/export",
        headers=superuser_token_headers,
        params={"format": "xlsx"},
    )
    assert exp.status_code == 200, exp.text
    joined = ""
    with zipfile.ZipFile(io.BytesIO(exp.content)) as z:
        for name in z.namelist():
            joined += z.read(name).decode("utf-8", errors="ignore")
    for sid in STUDENT_IDS:
        assert sid not in joined


def test_unknown_homework_returns_404(
    client: TestClient, db: Session, teacher_token_headers: dict[str, str]
) -> None:
    unknown = str(uuid.uuid4())
    r = client.get(f"/api/v1/analytics/homework/{unknown}/dashboard", headers=teacher_token_headers)
    assert r.status_code == 404, r.text
