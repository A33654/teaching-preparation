# -*- coding: utf-8 -*-
"""
测试环境根配置（离线可跑）：

沙箱/本地无 PostgreSQL / Neo4j / LLM 时，本文件在导入期完成三件事，
使 L0/L1 测试无需外部服务即可运行：
  1. 把 app.core.db.engine 替换为「文件型 SQLite」，并把所有 UUID 列换成
     自定义 GUID 类型（兼容 str/UUID 双向绑定 —— SQLite 原生 Uuid 只接受
     UUID 对象，而 JWT 中的 sub 是字符串，直接查会报 'str' has no 'hex'）。
  2. Mock Neo4j driver（get_neo4j_driver 返回 MagicMock）。
  3. Mock LLM（ChatOpenAI / get_chat_model 返回桩对象）。

保留原项目 fixtures（client / superuser_token_headers / normal_user_token_headers），
并新增 teacher / admin 令牌与造数辅助。
"""
from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Generator
from unittest.mock import MagicMock

# ---- 必须在导入 app 之前设置 ----
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("SEED_DEMO_ON_STARTUP", "false")  # 避免启动时连 Neo4j 灌库

from sqlalchemy import String  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402
from sqlalchemy.types import TypeDecorator  # noqa: E402

# ===================== 1) SQLite + UUID 兼容 =====================
# 说明：使用 :memory: + StaticPool（单连接共享）。
#  - 普通 :memory: 每个连接是独立库 → create_all 建表后查询不到（no such table）；
#  - 文件型 SQLite 在 Windows 上常被上次进程占用，remove 失败会导致测试库无法重置
#    （表现为 UNIQUE constraint failed）。StaticPool 同时规避这两个问题。


class GUID(TypeDecorator):
    """SQLite 下兼容 str/UUID 双向绑定的 UUID 类型。"""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        if isinstance(value, _uuid.UUID):
            return value
        try:
            return _uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return value


import app.core.db as _dbmod  # noqa: E402

from sqlalchemy.pool import StaticPool  # noqa: E402

_engine_sqlite = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# 在 create_all 之前，把所有 UUID 列替换为 GUID
from sqlalchemy import Uuid as _SaUuid  # noqa: E402

for _table in SQLModel.metadata.tables.values():
    for _col in _table.columns:
        if isinstance(_col.type, _SaUuid):
            _col.type = GUID()

SQLModel.metadata.create_all(_engine_sqlite)
_dbmod.engine = _engine_sqlite  # get_db 在调用时读取模块全局，故此处替换即可

# ===================== 2) Mock Neo4j =====================
import app.core.neo4j as _neo4jmod  # noqa: E402

_neo4jmod.get_neo4j_driver = lambda: MagicMock()
_neo4jmod.init_neo4j_constraints = lambda *a, **k: None

# ===================== 3) Mock LLM =====================
import app.agent.llm as _agent_llm  # noqa: E402

if hasattr(_agent_llm, "get_chat_model"):
    _agent_llm.get_chat_model = lambda *a, **k: MagicMock()
if hasattr(_agent_llm, "get_llm"):
    _agent_llm.get_llm = lambda *a, **k: MagicMock()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import init_db  # noqa: E402
from app.main import app  # noqa: E402


# ===================== fixtures =====================
@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session, None, None]:
    with Session(_engine_sqlite) as session:
        try:
            init_db(session)
        except Exception:  # noqa: BLE001 - 演示库/Neo4j 不可用时不影响
            pass
        yield session


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str, password: str) -> str | None:
    r = client.post(
        "/api/v1/login/access-token",
        data={"username": email, "password": password},
    )
    if r.status_code == 200:
        return r.json().get("access_token")
    return None


@pytest.fixture(scope="session")
def superuser_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    """超管令牌：优先用 .env 的 FIRST_SUPERUSER，失败则现场创建。"""
    token = _login(client, settings.FIRST_SUPERUSER, settings.FIRST_SUPERUSER_PASSWORD)
    if not token:
        from app import crud
        from app.models import UserCreate

        user = crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
        if not user:
            user = crud.create_user(
                session=db,
                user_create=UserCreate(
                    email=settings.FIRST_SUPERUSER,
                    password=settings.FIRST_SUPERUSER_PASSWORD,
                    is_superuser=True,
                ),
            )
        token = _login(client, settings.FIRST_SUPERUSER, settings.FIRST_SUPERUSER_PASSWORD)
    assert token, f"超管登录失败: {settings.FIRST_SUPERUSER}"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    """普通用户令牌（沿用项目原实现，供既有 tests/api/routes 使用）。"""
    from tests.utils.user import authentication_token_from_email

    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )


@pytest.fixture(scope="session")
def admin_token_headers(superuser_token_headers: dict[str, str]) -> dict[str, str]:
    """管理端（本项目由超管兼任教研管理员）。"""
    return superuser_token_headers


@pytest.fixture(scope="session")
def teacher_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    """普通教师账号（不存在则创建）。"""
    from app import crud
    from app.models import UserCreate

    email = "qa_teacher@example.com"
    pwd = "teacher123456"
    if not crud.get_user_by_email(session=db, email=email):
        crud.create_user(session=db, user_create=UserCreate(email=email, password=pwd))
    token = _login(client, email, pwd)
    assert token, "教师登录失败"
    return {"Authorization": f"Bearer {token}"}
