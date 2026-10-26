# -*- coding: utf-8 -*-
"""L1 接口功能测试：知识点图谱（knowledge_points，数据源为 Neo4j，用内存替身驱动）。

覆盖：CRUD / 关系 / 子图 / 搜索 / 章节联动 / 考点误区；含 401/403/404 与权限隔离。
"""
from __future__ import annotations

import pytest

API = "/api/v1"


def _create_kp(client, headers, name="知识点X", subject="数学"):
    return client.post(
        f"{API}/knowledge-points/",
        headers=headers,
        json={"name": name, "subject": subject, "description": "desc", "difficulty": 3, "is_key_point": True},
    )


class TestKnowledgePointCRUD:
    def test_create_and_get(self, client, teacher_token_headers):
        """✅ 正常：创建知识点 -> 详情可取"""
        c = _create_kp(client, teacher_token_headers)
        assert c.status_code == 200, c.text
        kp_id = c.json()["id"]
        g = client.get(f"{API}/knowledge-points/{kp_id}", headers=teacher_token_headers)
        assert g.status_code == 200 and g.json()["id"] == kp_id

    def test_list_and_full_graph(self, client, teacher_token_headers):
        """✅ 正常：列表 + 全图（含预置节点）"""
        lst = client.get(f"{API}/knowledge-points/", headers=teacher_token_headers)
        assert lst.status_code == 200 and lst.json()["count"] >= 1
        g = client.get(f"{API}/knowledge-points/graph/full", headers=teacher_token_headers)
        assert g.status_code == 200
        assert "nodes" in g.json() and "edges" in g.json()

    def test_create_empty_name(self, client, teacher_token_headers):
        """🈳 空白值：name 为空 -> 422（KnowledgePointCreate.name 有 min_length）"""
        r = client.post(f"{API}/knowledge-points/", headers=teacher_token_headers, json={"name": "", "subject": "数学"})
        assert r.status_code == 422

    def test_get_missing(self, client, teacher_token_headers):
        """❌ 错误：不存在知识点 -> 404"""
        r = client.get(f"{API}/knowledge-points/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers)
        assert r.status_code == 404

    def test_get_no_auth(self, client):
        """❌ 错误：未登录 -> 401"""
        r = client.get(f"{API}/knowledge-points/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 401

    def test_update_and_delete(self, client, teacher_token_headers):
        """✅ 正常：更新 -> 删除"""
        kp_id = _create_kp(client, teacher_token_headers).json()["id"]
        u = client.put(f"{API}/knowledge-points/{kp_id}", headers=teacher_token_headers, json={"name": "新名"})
        assert u.status_code == 200 and u.json()["name"] == "新名"
        d = client.delete(f"{API}/knowledge-points/{kp_id}", headers=teacher_token_headers)
        assert d.status_code == 200
        assert client.get(f"{API}/knowledge-points/{kp_id}", headers=teacher_token_headers).status_code == 404


class TestAccessControl:
    def test_teacher_cannot_access_others_kp(self, client, teacher_token_headers, patch_neo4j):
        """❌ 错误：访问他人知识点 -> 403（组织/owner 隔离）"""
        # 注入一个归属别人的知识点
        foreign = patch_neo4j.create_knowledge_point(owner_id="11111111-1111-1111-1111-111111111111", name="别人的")
        fid = foreign["id"]
        r = client.get(f"{API}/knowledge-points/{fid}", headers=teacher_token_headers)
        assert r.status_code == 403

    def test_superuser_sees_any_kp(self, client, superuser_token_headers, patch_neo4j):
        """✅ 正常：超管可访问任意知识点（跨组织）"""
        foreign = patch_neo4j.create_knowledge_point(owner_id="22222222-2222-2222-2222-222222222222", name="某组织")
        fid = foreign["id"]
        r = client.get(f"{API}/knowledge-points/{fid}", headers=superuser_token_headers)
        assert r.status_code == 200


class TestRelationsAndSearch:
    def test_relation_crud(self, client, teacher_token_headers):
        """✅ 正常：创建关系 -> 列表 -> 删除"""
        a = _create_kp(client, teacher_token_headers, name="A").json()["id"]
        b = _create_kp(client, teacher_token_headers, name="B").json()["id"]
        rel = client.post(f"{API}/knowledge-points/{a}/relations", headers=teacher_token_headers,
                          json={"target_id": b, "relation_type": "prerequisite"})
        assert rel.status_code == 200, rel.text
        lst = client.get(f"{API}/knowledge-points/{a}/relations", headers=teacher_token_headers)
        assert lst.status_code == 200 and len(lst.json()) >= 1
        d = client.delete(f"{API}/knowledge-points/{a}/relations", headers=teacher_token_headers,
                          params={"target_id": b, "relation_type": "prerequisite"})
        assert d.status_code == 200

    def test_relation_target_missing(self, client, teacher_token_headers):
        """❌ 错误：关系指向不存在目标 -> 404"""
        a = _create_kp(client, teacher_token_headers, name="C").json()["id"]
        r = client.post(f"{API}/knowledge-points/{a}/relations", headers=teacher_token_headers,
                        json={"target_id": "00000000-0000-0000-0000-000000000000", "relation_type": "prerequisite"})
        assert r.status_code == 404

    def test_subgraph_and_search(self, client, teacher_token_headers):
        """✅ 正常：子图检索 + 关键词搜索"""
        kp_id = _create_kp(client, teacher_token_headers, name="检索点").json()["id"]
        sg = client.get(f"{API}/knowledge-points/{kp_id}/subgraph", headers=teacher_token_headers)
        assert sg.status_code == 200 and "nodes" in sg.json()
        s = client.post(f"{API}/knowledge-points/search", headers=teacher_token_headers, json={"query": "检索点", "top_k": 5})
        assert s.status_code == 200 and "results" in s.json()

    def test_chapter_context(self, client, teacher_token_headers):
        """✅ 正常：章节联动返回覆盖度判定与教学顺序等"""
        # 命中预置核心知识点（函数与导数 is_key_point=True）
        r = client.post(f"{API}/knowledge-points/chapter-context", headers=teacher_token_headers,
                        json={"chapter": "函数与导数", "subject": "数学"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "coverage" in body and "teaching_order" in body and "knowledge_points" in body
        # 未命中章节 -> missing 兜底
        miss = client.post(f"{API}/knowledge-points/chapter-context", headers=teacher_token_headers,
                           json={"chapter": "完全不存在的章节XYZ", "subject": "数学"})
        assert miss.status_code == 200 and miss.json()["coverage"] == "missing"


class TestExamPointsAndMisconceptions:
    def test_exam_point_lifecycle(self, client, teacher_token_headers):
        """✅ 正常：知识点下新增考点 -> 列表 -> 删除"""
        kp_id = _create_kp(client, teacher_token_headers).json()["id"]
        c = client.post(f"{API}/knowledge-points/{kp_id}/exam-points", headers=teacher_token_headers,
                        json={"name": "考点1", "level": "理解"})
        assert c.status_code == 200, c.text
        eid = c.json()["id"]
        lst = client.get(f"{API}/knowledge-points/{kp_id}/exam-points", headers=teacher_token_headers)
        assert lst.status_code == 200 and len(lst.json()["data"]) >= 1
        d = client.delete(f"{API}/knowledge-points/{kp_id}/exam-points/{eid}", headers=teacher_token_headers)
        assert d.status_code == 200

    def test_misconception_lifecycle(self, client, teacher_token_headers):
        """✅ 正常：知识点下新增误区 -> 列表 -> 删除"""
        kp_id = _create_kp(client, teacher_token_headers).json()["id"]
        c = client.post(f"{API}/knowledge-points/{kp_id}/misconceptions", headers=teacher_token_headers,
                        json={"content": "误区内容", "correction": "纠正"})
        assert c.status_code == 200
        mid = c.json()["id"]
        lst = client.get(f"{API}/knowledge-points/{kp_id}/misconceptions", headers=teacher_token_headers)
        assert lst.status_code == 200 and len(lst.json()["data"]) >= 1
        d = client.delete(f"{API}/knowledge-points/{kp_id}/misconceptions/{mid}", headers=teacher_token_headers)
        assert d.status_code == 200
