# -*- coding: utf-8 -*-
"""L1 接口功能测试的共用配置（tests/api/l1 专属，不影响 tests/api/routes 既有用例）。

提供：
  - patch_neo4j  : 把 KnowledgeGraphRepository 替换为内存替身（有状态，跨同测试内调用）
  - patch_llm     : 把各路由模块内导入的 LangGraph 图函数替换为离线桩
  - seed_org      : 创建租户 Organization 并分配给教师/超管（lesson_plans 等要求 org_id）
  - helpers       : 通过 API 造数的便捷函数
"""
from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest
from sqlmodel import select

from app.models import Organization, User


@pytest.fixture(autouse=True)
def patch_neo4j():
    """用内存替身替换 Neo4j 仓储，使图谱相关接口离线可测。

    关键：各路由模块用 `from app.knowledge_graph import KnowledgeGraphRepository`
    在加载期就把类绑定进了自己的命名空间，因此必须 patch 路由模块本身，
    而非源模块（否则仍是真实仓储 —— 曾导致 dashboard 500）。
    """
    from tests.api.l1.fakes import FakeKnowledgeGraphRepository

    import app.api.routes.admin as admin_rt
    import app.api.routes.chat as chat_rt
    import app.api.routes.curriculum as curriculum_rt
    import app.api.routes.documents as docs_rt
    import app.api.routes.knowledge_points as kp_rt
    import app.api.routes.lesson_plans as lp_rt

    fake = FakeKnowledgeGraphRepository()

    # 同一测试内所有 KnowledgeGraphRepository() 都返回同一个有状态实例
    class _FakeCls:
        def __new__(cls):
            return fake

    targets = [admin_rt, chat_rt, curriculum_rt, docs_rt, kp_rt, lp_rt]
    with ExitStack() as stack:
        for m in targets:
            stack.enter_context(patch.object(m, "KnowledgeGraphRepository", _FakeCls))
        yield fake


@pytest.fixture(autouse=True)
def patch_llm():
    """把路由模块中已导入的 LangGraph 图函数替换为离线桩。

    注意：路由用 `from app.agent.graphs import run_x` 在模块加载期就把名字
    绑定到了自己的命名空间，因此必须 patch 路由模块，而非源模块。
    """
    from tests.api.l1.fakes import (
        fake_astream_chat_events,
        fake_build_chat_graph,
        fake_extraction,
        fake_lesson_plan,
        fake_ppt_outline,
        fake_summarize,
    )

    import app.api.routes.chat as chat_rt
    import app.api.routes.documents as docs_rt
    import app.api.routes.lesson_plans as lp_rt
    import app.api.routes.summarize as sm_rt

    with (
        patch.object(lp_rt, "run_lesson_plan", fake_lesson_plan),
        patch.object(lp_rt, "run_summarize", fake_summarize),
        patch.object(sm_rt, "run_ppt_outline", fake_ppt_outline),
        patch.object(sm_rt, "run_summarize", fake_summarize),
        patch.object(docs_rt, "run_extraction", fake_extraction),
        patch.object(chat_rt, "astream_chat_events", fake_astream_chat_events),
        patch.object(chat_rt, "build_chat_graph", fake_build_chat_graph),
    ):
        yield


@pytest.fixture(autouse=True)
def seed_org(db, teacher_token_headers, superuser_token_headers):
    """创建租户并分配给教师/超管，返回 org_id。

    lesson_plans 等接口要求 user.org_id 非空且对应 Organization 存在；
    get_current_user 每次请求都会重新从库读取用户，故这里改库即生效。
    """
    org = db.exec(select(Organization).where(Organization.name == "测试学校L1")).first()
    if not org:
        org = Organization(name="测试学校L1")
        db.add(org)
        db.commit()
        db.refresh(org)

    teacher = db.exec(select(User).where(User.email == "qa_teacher@example.com")).first()
    if teacher and teacher.org_id != org.id:
        teacher.org_id = org.id
        db.add(teacher)
    su = db.exec(select(User).where(User.email == "qa_superuser@example.com")).first()
    if su and su.org_id != org.id:
        su.org_id = org.id
        db.add(su)
    db.commit()
    return org.id


@pytest.fixture
def teacher_user(db) -> User:
    return db.exec(select(User).where(User.email == "qa_teacher@example.com")).first()


@pytest.fixture
def superuser_user(db) -> User:
    return db.exec(select(User).where(User.email == "qa_superuser@example.com")).first()
