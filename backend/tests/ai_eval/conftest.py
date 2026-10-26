# -*- coding: utf-8 -*-
"""L3 AI 评测的共用 fixture：复用 L1 的离线补丁（Neo4j 替身 + LLM 桩 + org 种子）。"""
from __future__ import annotations

from tests.api.l1.conftest import (  # noqa: F401
    patch_llm,
    patch_neo4j,
    seed_org,
    superuser_user,
    teacher_user,
)
