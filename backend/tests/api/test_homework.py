# -*- coding: utf-8 -*-
"""FR-01 / FR-02 / FR-03 作业功能验收测试（离线：SQLite + Mock Neo4j）。"""
import hashlib
import uuid

import pytest
from sqlmodel import select

from app.core.config import settings
from app.models import GradeLevel, LessonPlan, LessonPlanStatus, User, Visibility


def _fake_kps(ids):
    return [
        {
            "id": i,
            "name": f"知识点-{i}",
            "subject": "物理",
            "grade_level": "初中",
            "difficulty": 1,
            "is_key_point": False,
            "owner_id": None,
            "created_at": None,
            "description": None,
        }
        for i in ids
    ]


@pytest.fixture
def mock_kp(monkeypatch):
    # 让作业详情/列表的知识点解析返回可控数据（否则 Mock 的 Neo4j 会崩）
    # 注意：赋到类上的函数会按描述符协议绑定 self，故签名需带 self
    monkeypatch.setattr(
        "app.knowledge_graph.repository.KnowledgeGraphRepository.get_many_knowledge_points",
        lambda self, ids: _fake_kps(ids),
    )


def _teacher_id(db):
    return db.exec(select(User).where(User.email == "qa_teacher@example.com")).first().id


def _make_lesson_plan(db, teacher_id):
    lp = LessonPlan(
        title="光的折射",
        subject="物理",
        grade_level=GradeLevel.JUNIOR,
        owner_id=teacher_id,
        org_id=None,
        visibility=Visibility.PRIVATE,
        status=LessonPlanStatus.DRAFT,
        knowledge_point_ids=["kp-1", "kp-2"],
        classroom_exercises=[
            {
                "id": "ex-1",
                "type": "choice",
                "stem": "光从空气斜射入水中，折射角与入射角的关系是？",
                "options": ["大于", "小于", "等于", "无关"],
                "correct_option": 1,
                "answers": [],
                "reference_answer": "",
            },
            {
                "id": "ex-2",
                "type": "fill",
                "stem": "光从空气进入水中，折射角____入射角（填大于/小于）。",
                "options": [],
                "correct_option": None,
                "answers": ["小于"],
                "reference_answer": "",
            },
        ],
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


# ==================== FR-01：从教案一键生成作业 ====================

def _generate_homework(client, headers, db):
    """辅助：造一份带课堂习题的教案，并一键生成作业。"""
    teacher_id = _teacher_id(db)
    lp = _make_lesson_plan(db, teacher_id)
    r = client.post(
        f"/api/v1/homework/generate-from/{lp.id}",
        json={},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_fr01_generate_from_lesson_plan(client, teacher_token_headers, db, mock_kp):
    hw = _generate_homework(client, teacher_token_headers, db)
    # 题目与知识点预填
    assert len(hw["questions"]) == 2
    # 题目自动继承教案关联的知识点
    for q in hw["questions"]:
        assert q["knowledge_point_ids"] == ["kp-1", "kp-2"]
    # 知识点题库解析到位
    assert {kp["id"] for kp in hw["knowledge_points"]} == {"kp-1", "kp-2"}
    assert hw["status"] == "draft"


# ==================== FR-02：编辑 + 题型 + 知识点校验拦截 ====================

def test_fr02_add_short_question_with_kp(client, teacher_token_headers, db, mock_kp):
    hw = _generate_homework(client, teacher_token_headers, db)
    questions = list(hw["questions"])
    # 新增一道简答题并选择知识点 kp-3
    questions.append(
        {
            "id": "ex-3",
            "type": "short",
            "stem": "简述折射定律的内容。",
            "options": [],
            "correct_option": None,
            "answers": [],
            "reference_answer": "折射光线、入射光线和法线共面……",
            "knowledge_point_ids": ["kp-3"],
        }
    )
    r = client.put(
        f"/api/v1/homework/{hw['id']}",
        json={"questions": questions},
        headers=teacher_token_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    short = [q for q in updated["questions"] if q["type"] == "short"]
    assert short, "简答题未被保存"
    assert short[0]["knowledge_point_ids"] == ["kp-3"]


def test_fr02_publish_blocks_question_without_kp(client, teacher_token_headers, db, mock_kp):
    hw = _generate_homework(client, teacher_token_headers, db)
    questions = list(hw["questions"])
    # 故意把第一题的知识点清空
    questions[0]["knowledge_point_ids"] = []
    client.put(
        f"/api/v1/homework/{hw['id']}",
        json={"questions": questions},
        headers=teacher_token_headers,
    )
    # 提交（发布）时未关联知识点的题被拦截
    r = client.post(
        f"/api/v1/homework/{hw['id']}/publish",
        headers=teacher_token_headers,
    )
    assert r.status_code == 422, r.text
    assert "未关联知识点" in r.json()["detail"]


# ==================== FR-03：发布 + 模拟提交（学号哈希） ====================

def test_fr03_publish_then_simulate_submit(client, teacher_token_headers, db, mock_kp):
    hw = _generate_homework(client, teacher_token_headers, db)
    # 全部题目均带知识点 -> 可发布
    r = client.post(
        f"/api/v1/homework/{hw['id']}/publish",
        headers=teacher_token_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"

    student_id = "2021001"
    answers = [{"question_id": q["id"], "content": "折射角小于入射角"} for q in hw["questions"]]
    r = client.post(
        f"/api/v1/homework/{hw['id']}/simulate-submit",
        json={"student_id": student_id, "answers": answers},
        headers=teacher_token_headers,
    )
    assert r.status_code == 200, r.text
    sub = r.json()
    # 状态 = 已提交
    assert sub["status"] == "submitted"
    # 学号以哈希存储（不可逆、与明文不同）
    expected_hash = hashlib.sha256(
        (student_id + settings.SECRET_KEY).encode("utf-8")
    ).hexdigest()
    assert sub["student_id_hash"] == expected_hash
    assert sub["student_id_hash"] != student_id

    # 列表可查到该提交
    r2 = client.get(
        f"/api/v1/homework/{hw['id']}/submissions",
        headers=teacher_token_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["count"] == 1
