# -*- coding: utf-8 -*-
"""L1 接口功能测试：学科 / 教材 / 章节（curriculum，DB + 图谱同步 try/except 降级）。

覆盖：正常 / 空白值 / 错误 / 边界；含 Neo4j 不可用时的优雅降级路径。
"""
from __future__ import annotations

import pytest

from tests.api.l1.helpers import create_chapter, create_subject, create_textbook

API = "/api/v1"


class TestSubjects:
    def test_create_and_list(self, client, teacher_token_headers):
        """✅ 正常：创建学科并出现在本人列表"""
        c = create_subject(client, teacher_token_headers)
        assert c.status_code == 200, c.text
        sid = c.json()["id"]
        lst = client.get(f"{API}/curriculum/subjects", headers=teacher_token_headers)
        assert lst.status_code == 200
        assert any(s["id"] == sid for s in lst.json()["data"])

    def test_create_empty_name(self, client, teacher_token_headers):
        """🈳 空白值：name 为空应被校验拒绝（422）—— SubjectCreate.name 已加 min_length=1"""
        r = client.post(f"{API}/curriculum/subjects", headers=teacher_token_headers, json={"name": ""})
        assert r.status_code == 422

    def test_delete_missing(self, client, teacher_token_headers):
        """❌ 错误：删除不存在学科 → 404"""
        r = client.delete(f"{API}/curriculum/subjects/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers)
        assert r.status_code == 404

    def test_delete_invalid_uuid(self, client, teacher_token_headers):
        """❌ 错误：非法 UUID → 400"""
        r = client.delete(f"{API}/curriculum/subjects/xxx", headers=teacher_token_headers)
        assert r.status_code == 400


class TestTextbooks:
    def test_create_and_list(self, client, teacher_token_headers):
        """✅ 正常：创建教材（自动建根章节）并出现在列表"""
        sub = create_subject(client, teacher_token_headers)
        sid = sub.json()["id"]
        tb = create_textbook(client, teacher_token_headers, sid, name="人教版化学")
        assert tb.status_code == 200, tb.text
        tid = tb.json()["id"]
        lst = client.get(f"{API}/curriculum/textbooks", headers=teacher_token_headers)
        assert any(t["id"] == tid for t in lst.json()["data"])

    def test_create_invalid_subject_id(self, client, teacher_token_headers):
        """❌ 错误：subject_id 非 UUID 应被拒绝（422）—— TextbookCreate.subject_id 已改为 UUID 类型"""
        r = client.post(
            f"{API}/curriculum/textbooks", headers=teacher_token_headers,
            json={"name": "教材", "subject_id": "not-uuid"},
        )
        assert r.status_code == 422

    def test_delete_missing(self, client, teacher_token_headers):
        """❌ 错误：删除不存在教材 → 404"""
        r = client.delete(f"{API}/curriculum/textbooks/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers)
        assert r.status_code == 404


class TestChapters:
    def _make_chain(self, client, headers):
        sub = create_subject(client, headers)
        tb = create_textbook(client, headers, sub.json()["id"], name="人教版生物")
        tb_id = tb.json()["id"]
        ch = create_chapter(client, headers, tb_id, title="第一章", level=1)
        return tb_id, ch.json()["id"]

    def test_create_list_tree(self, client, teacher_token_headers):
        """✅ 正常：建章节并出现在章节树（扁平转树）"""
        tb_id, ch_id = self._make_chain(client, teacher_token_headers)
        lst = client.get(f"{API}/curriculum/chapters/{tb_id}", headers=teacher_token_headers)
        assert lst.status_code == 200
        assert any(c["id"] == ch_id for c in lst.json())

    def test_reorder_and_update(self, client, teacher_token_headers):
        """✅ 正常：重排层级 + 改名"""
        tb_id, ch_id = self._make_chain(client, teacher_token_headers)
        re = client.put(f"{API}/curriculum/chapters/{ch_id}/reorder", headers=teacher_token_headers, params={"new_order": 5})
        assert re.status_code == 200
        up = client.put(f"{API}/curriculum/chapters/{ch_id}", headers=teacher_token_headers, params={"title": "第一章（修订）"})
        assert up.status_code == 200

    def test_invalid_textbook_id(self, client, teacher_token_headers):
        """❌ 错误：textbook_id 非法 → 400"""
        r = client.get(f"{API}/curriculum/chapters/not-uuid", headers=teacher_token_headers)
        assert r.status_code == 400

    def test_delete_missing(self, client, teacher_token_headers):
        """❌ 错误：删除不存在章节 → 404"""
        r = client.delete(f"{API}/curriculum/chapters/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers)
        assert r.status_code == 404


class TestDashboard:
    def test_dashboard_returns_structure(self, client, teacher_token_headers):
        """✅ 正常：学科仪表盘返回 subject/docs/lesson_plans/ppts/knowledge_points"""
        sub = create_subject(client, teacher_token_headers)
        sid = sub.json()["id"]
        r = client.get(f"{API}/curriculum/dashboard/{sid}", headers=teacher_token_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("subject", "documents", "lesson_plans", "ppts", "knowledge_points"):
            assert k in body

    def test_dashboard_invalid_id(self, client, teacher_token_headers):
        """❌ 错误：subject_id 非法 → 400"""
        r = client.get(f"{API}/curriculum/dashboard/not-uuid", headers=teacher_token_headers)
        assert r.status_code == 400

    def test_dashboard_missing_subject(self, client, teacher_token_headers):
        """❌ 错误：学科不存在 → 404"""
        r = client.get(f"{API}/curriculum/dashboard/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers)
        assert r.status_code == 404
