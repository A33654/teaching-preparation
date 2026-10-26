# -*- coding: utf-8 -*-
"""L1 测试用的「内存版」替身：Neo4j 知识图谱 + LangGraph LLM 图。

用于在 sandbox（无 Neo4j / 无 LLM Key）下跑通所有原本依赖图谱与大模型
的接口。替身行为尽量贴近真实：返回与 Pydantic 响应模型字段一致的字典，
以支持 ``KnowledgePointOut(**kp)`` 这类解包。

仅在 tests/api/l1 目录下的测试中使用，不污染生产代码与既有 tests/api/routes。
"""
from __future__ import annotations

import uuid


def _kp(
    kp_id: str | None = None,
    name: str = "知识点",
    subject: str = "数学",
    description: str | None = None,
    grade_level: str | None = "高中",
    difficulty: int = 2,
    is_key_point: bool = False,
    owner_id: str | None = None,
    org_id: str | None = None,
) -> dict:
    return {
        "id": kp_id or str(uuid.uuid4()),
        "name": name,
        "subject": subject,
        "description": description,
        "grade_level": grade_level,
        "difficulty": difficulty,
        "is_key_point": is_key_point,
        "owner_id": owner_id,
        "org_id": org_id,
        "created_at": "2026-01-01T00:00:00Z",
    }


class FakeKnowledgeGraphRepository:
    """进程内内存知识图谱替身，按 id 维护节点 / 关系 / 考点 / 误区。"""

    def __init__(self) -> None:
        self._kps: dict[str, dict] = {}
        self._relations: list[dict] = []
        self._exam_points: dict[str, dict] = {}
        self._misconceptions: dict[str, dict] = {}
        self._items: dict[str, dict] = {}
        # 预置一个核心知识点，便于知识库覆盖判定等逻辑有真实输入
        sample = _kp(name="函数与导数", subject="数学", is_key_point=True, difficulty=4)
        self._kps[sample["id"]] = sample

    # ---------- 知识点节点 ----------
    def get_knowledge_point(self, kp_id: str) -> dict | None:
        return self._kps.get(kp_id)

    def get_many_knowledge_points(self, ids: list[str]) -> list[dict]:
        return [self._kps[i] for i in ids if i in self._kps]

    def list_knowledge_points(
        self, owner_id=None, org_id=None, skip=0, limit=100,
        subject=None, grade_level=None, search=None,
    ) -> tuple[list[dict], int]:
        items = list(self._kps.values())
        if subject:
            items = [k for k in items if k.get("subject") == subject]
        if grade_level:
            items = [k for k in items if k.get("grade_level") == grade_level]
        if search:
            items = [k for k in items if search in (k.get("name") or "")]
        return items[skip : skip + limit], len(items)

    def create_knowledge_point(self, owner_id=None, name="知识点", subject="通用",
                               description=None, grade_level=None, difficulty=3,
                               is_key_point=False, org_id=None, **kwargs) -> dict:
        kp = _kp(
            name=name, subject=subject, description=description,
            grade_level=grade_level, difficulty=difficulty,
            is_key_point=is_key_point, owner_id=owner_id, org_id=org_id,
        )
        self._kps[kp["id"]] = kp
        return kp

    def update_knowledge_point(self, kp_id: str, **fields) -> dict | None:
        kp = self._kps.get(kp_id)
        if not kp:
            return None
        for k, v in fields.items():
            kp[k] = v
        return kp

    def delete_knowledge_point(self, kp_id: str) -> None:
        self._kps.pop(kp_id, None)

    def find_by_name(self, name: str, org_id=None) -> dict | None:
        for kp in self._kps.values():
            if kp["name"] == name:
                return kp
        return None

    def count_knowledge_points(self, org_id=None) -> int:
        return len(self._kps)

    # ---------- 关系 ----------
    def create_relation(self, source_id: str, target_id: str, relation_type: str = "related_to") -> dict | None:
        if source_id not in self._kps or target_id not in self._kps:
            return None
        rel = {"source_id": source_id, "target_id": target_id, "relation_type": relation_type}
        self._relations.append(rel)
        return rel

    def get_relations(self, kp_id: str) -> list[dict]:
        return [r for r in self._relations if r["source_id"] == kp_id or r["target_id"] == kp_id]

    def delete_relation(self, source_id: str, target_id: str, relation_type: str = "related_to") -> bool:
        before = len(self._relations)
        self._relations = [
            r for r in self._relations
            if not (r["source_id"] == source_id and r["target_id"] == target_id
                    and r["relation_type"] == relation_type)
        ]
        return len(self._relations) != before

    def get_full_graph(self, org_id=None) -> dict:
        return {"nodes": list(self._kps.values()), "edges": self._relations}

    def get_subgraph(self, kp_id: str, depth: int = 2) -> dict:
        return {"nodes": [self._kps[kp_id]] if kp_id in self._kps else [], "edges": self._relations}

    def search_knowledge_points(self, query, owner_id=None, org_id=None, top_k=10) -> list[dict]:
        hits = [k for k in self._kps.values() if query and query in (k.get("name") or "")]
        return hits[:top_k]

    # ---------- 前置依赖 ----------
    def get_prerequisites(self, kp_id: str) -> list[dict]:
        return [self._kps[r["source_id"]] for r in self._relations
                if r["target_id"] == kp_id and r["relation_type"] == "prerequisite"]

    def get_prerequisite_chain(self, kp_id: str, max_depth: int = 3) -> list[dict]:
        return [{"name": "前置知识A", "depth": 1}]

    # ---------- 考点 / 误区 ----------
    def get_exam_points(self, kp_id: str) -> list[dict]:
        return [e for e in self._exam_points.values() if e.get("kp_id") == kp_id]

    def create_exam_point(self, owner_id=None, name="考点", level="理解", description="", kp_id=None) -> dict:
        eid = str(uuid.uuid4())
        ep = {"id": eid, "name": name, "level": level, "description": description, "kp_id": kp_id}
        self._exam_points[eid] = ep
        return ep

    def link_kp_exam_point(self, kp_id: str, exam_id: str) -> None:
        if exam_id in self._exam_points:
            self._exam_points[exam_id]["kp_id"] = kp_id

    def delete_exam_point(self, exam_id: str) -> None:
        self._exam_points.pop(exam_id, None)

    def get_misconceptions(self, kp_id: str) -> list[dict]:
        return [m for m in self._misconceptions.values() if m.get("kp_id") == kp_id]

    def create_misconception(self, owner_id=None, content="误区", correction="", kp_id=None) -> dict:
        mid = str(uuid.uuid4())
        m = {"id": mid, "content": content, "correction": correction, "kp_id": kp_id}
        self._misconceptions[mid] = m
        return m

    def link_kp_misconception(self, kp_id: str, mis_id: str) -> None:
        if mis_id in self._misconceptions:
            self._misconceptions[mis_id]["kp_id"] = kp_id

    def delete_misconception(self, mis_id: str) -> None:
        self._misconceptions.pop(mis_id, None)

    # ---------- 教案 <-> 图谱 ----------
    def link_lesson_plan_knowledge_points(self, lp_id: str, kp_ids: list[str]) -> None:
        pass

    def create_knowledge_item(self, org_id=None, owner_id=None, name="", subject=None,
                              grade_level=None, description="", snapshot_id=None, source="lesson_plan") -> dict:
        item = {"id": str(uuid.uuid4()), "name": name, "subject": subject,
                "grade_level": grade_level, "description": description,
                "snapshot_id": snapshot_id, "source": source}
        self._items[item["id"]] = item
        return item

    # ---------- 质量检查 ----------
    def graph_quality_check(self) -> dict:
        return {"loops": [], "orphans": [], "missing_prereq": []}


# ===================== LLM 替身 =====================
# 让 LangGraph 教案/概括/PPT/抽取/问答在离线环境返回可解析的结构化结果。

def fake_lesson_plan(*args, **kwargs) -> dict:
    return {
        "lesson_plan": {
            "title": kwargs.get("chapter") or "函数与导数 教学设计",
            "subject": kwargs.get("subject") or "数学",
            "grade_level": kwargs.get("grade_level") or "高中",
            "teaching_objectives": "理解函数概念，掌握导数基本运算。",
            "teaching_process": "1. 导入；2. 新授；3. 练习；4. 小结。",
            "key_points": ["函数定义", "导数公式"],
            "difficult_points": ["复合函数求导"],
        },
        "graph_context": [{"id": "k1", "name": "函数"}],
        "verification_report": {"passed": True, "checks": ["结构完整"]},
    }


def fake_summarize(*args, **kwargs) -> dict:
    return {
        "summary": "本文概述了二次函数的基本性质与图像特征。",
        "key_topics": ["开口方向", "顶点坐标", "对称轴"],
        "suggested_approach": "以图像直观为主，配合代数推导。",
    }


def fake_ppt_outline(*args, **kwargs) -> list[dict]:
    return [
        {"title": "封面", "bullets": ["二次函数复习"]},
        {"title": "核心概念", "bullets": ["图像", "顶点", "判别式"]},
        {"title": "典型例题", "bullets": ["求最值", "判断根"]},
    ]


def fake_extraction(*args, **kwargs) -> dict:
    return {
        "subject": "数学",
        "kp_ids": [],
        "knowledge_points": [{"id": "x1", "name": "等差数列"}],
        "relations": [],
        "summary": "本文讲解了等差数列的通项公式与求和公式。",
    }


async def fake_astream_chat_events(graph, owner_id, user_profile, history, message):
    """模拟 LangGraph ReAct Agent 的事件流：token -> done。"""
    yield {"type": "token", "content": "二次"}
    yield {"type": "token", "content": "函数"}
    yield {"type": "token", "content": "是形如 f(x)=ax^2+bx+c 的函数。"}
    yield {"type": "done", "reply": "二次函数是形如 f(x)=ax^2+bx+c 的函数。", "sources": []}


class FakeChatGraph:
    """build_chat_graph 的替身返回对象（astream_chat_events 不依赖其实例内容）。"""
    pass


def fake_build_chat_graph(*args, **kwargs):
    return FakeChatGraph()
