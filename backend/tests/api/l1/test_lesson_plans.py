# -*- coding: utf-8 -*-
"""L1 接口功能测试：教案管理（lesson_plans，DB + 图谱 COVERS 同步 + LangGraph AI 生成 + RBAC 状态机）。

覆盖：正常 / 空白值 / 错误 / 边界；含 401/403/404、审核状态机与权限分离（README 重点验收项）。
"""
from __future__ import annotations

import pytest

from tests.api.l1.helpers import create_lesson_plan

API = "/api/v1"


class TestLessonPlanCRUD:
    def test_create_and_get_and_list(self, client, teacher_token_headers):
        """✅ 正常：创建 → 详情 → 出现在列表"""
        c = create_lesson_plan(client, teacher_token_headers, title="一次函数")
        assert c.status_code == 200, c.text
        lp_id = c.json()["id"]
        g = client.get(f"{API}/lesson-plans/{lp_id}", headers=teacher_token_headers)
        assert g.status_code == 200 and g.json()["id"] == lp_id
        lst = client.get(f"{API}/lesson-plans/", headers=teacher_token_headers)
        assert lst.status_code == 200
        assert any(x["id"] == lp_id for x in lst.json()["data"])

    def test_create_empty_title(self, client, teacher_token_headers):
        """🈳 空白值：title 为空 → 422（LessonPlanCreate.title 有 min_length）"""
        r = client.post(
            f"{API}/lesson-plans/", headers=teacher_token_headers,
            json={"title": "", "subject": "数学", "teaching_objectives": "x", "teaching_process": "y"},
        )
        assert r.status_code == 422

    def test_create_long_title_boundary(self, client, teacher_token_headers):
        """⚠️ 边界：title 超 255 字符 → 422（max_length）"""
        long_title = "教案" * 200
        r = client.post(
            f"{API}/lesson-plans/", headers=teacher_token_headers,
            json={"title": long_title, "subject": "数学", "teaching_objectives": "x", "teaching_process": "y"},
        )
        assert r.status_code == 422

    def test_get_missing(self, client, teacher_token_headers):
        """❌ 错误：不存在的教案 → 404"""
        r = client.get(f"{API}/lesson-plans/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers)
        assert r.status_code == 404

    def test_get_no_auth(self, client):
        """❌ 错误：未登录 → 401"""
        r = client.get(f"{API}/lesson-plans/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 401

    def test_update_and_delete(self, client, teacher_token_headers):
        """✅ 正常：更新标题 → 删除"""
        c = create_lesson_plan(client, teacher_token_headers, title="旧标题")
        lp_id = c.json()["id"]
        u = client.put(f"{API}/lesson-plans/{lp_id}", headers=teacher_token_headers, json={"title": "新标题"})
        assert u.status_code == 200 and u.json()["title"] == "新标题"
        d = client.delete(f"{API}/lesson-plans/{lp_id}", headers=teacher_token_headers)
        assert d.status_code == 200
        assert client.get(f"{API}/lesson-plans/{lp_id}", headers=teacher_token_headers).status_code == 404

    def test_update_missing(self, client, teacher_token_headers):
        """❌ 错误：更新不存在 → 404"""
        r = client.put(f"{API}/lesson-plans/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers, json={"title": "x"})
        assert r.status_code == 404


class TestAIGeneration:
    def test_ai_generate_creates_draft(self, client, teacher_token_headers):
        """✅ 正常：AI 生成（LangGraph 桩）返回结构化教案并落库为草稿"""
        r = client.post(
            f"{API}/lesson-plans/ai-generate", headers=teacher_token_headers,
            json={"subject": "数学", "grade_level": "高中", "chapter": "函数"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] and body["title"] and body["teaching_objectives"]
        # 落库后可按 id 取回
        g = client.get(f"{API}/lesson-plans/{body['id']}", headers=teacher_token_headers)
        assert g.status_code == 200

    def test_summarize_upload(self, client, teacher_token_headers):
        """✅ 正常：上传文档触发概括（LangGraph 桩）返回 summary/key_topics"""
        from io import BytesIO
        files = {"file": ("doc.txt", BytesIO("二次函数是形如 y=ax^2+bx+c 的函数，图像为抛物线。".encode("utf-8") * 20), "text/plain")}
        r = client.post(f"{API}/lesson-plans/summarize", headers=teacher_token_headers, files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "summary" in body and "key_topics" in body

    def test_summarize_empty_file(self, client, teacher_token_headers):
        """🈳 空白值：空内容文件 → 400（解析后文本过短）"""
        from io import BytesIO
        files = {"file": ("empty.txt", BytesIO(b""), "text/plain")}
        r = client.post(f"{API}/lesson-plans/summarize", headers=teacher_token_headers, files=files)
        assert r.status_code == 400


class TestReviewStateMachine:
    """draft → pending → approved/rejected → archived；权限分离验收。"""

    def _draft(self, client, headers, title="待审教案"):
        return create_lesson_plan(client, headers, title=title).json()["id"]

    def test_submit_approve_archive_by_reviewer(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：教师提交 → 审核员（超管）通过 → 归档"""
        lp_id = self._draft(client, teacher_token_headers)
        s = client.post(f"{API}/lesson-plans/{lp_id}/submit", headers=teacher_token_headers)
        assert s.status_code == 200 and s.json()["status"] == "pending"
        a = client.post(f"{API}/lesson-plans/{lp_id}/approve", headers=superuser_token_headers)
        assert a.status_code == 200 and a.json()["status"] == "approved"
        ar = client.post(f"{API}/lesson-plans/{lp_id}/archive", headers=superuser_token_headers)
        assert ar.status_code == 200 and ar.json()["status"] == "archived"

    def test_teacher_cannot_approve(self, client, teacher_token_headers):
        """❌ 错误：普通教师无审核权限，通过 → 403（README 权限分离验收项）"""
        lp_id = self._draft(client, teacher_token_headers)
        client.post(f"{API}/lesson-plans/{lp_id}/submit", headers=teacher_token_headers)
        a = client.post(f"{API}/lesson-plans/{lp_id}/approve", headers=teacher_token_headers)
        assert a.status_code == 403

    def test_reject_requires_comment(self, client, teacher_token_headers, superuser_token_headers):
        """❌ 错误：驳回必须填原因，缺原因 → 400"""
        lp_id = self._draft(client, teacher_token_headers)
        client.post(f"{API}/lesson-plans/{lp_id}/submit", headers=teacher_token_headers)
        r = client.post(f"{API}/lesson-plans/{lp_id}/reject", headers=superuser_token_headers, json={"comment": ""})
        assert r.status_code == 400

    def test_reject_then_resubmit(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：审核驳回（带原因）→ 教师重新提交回到 pending"""
        lp_id = self._draft(client, teacher_token_headers)
        client.post(f"{API}/lesson-plans/{lp_id}/submit", headers=teacher_token_headers)
        rj = client.post(f"{API}/lesson-plans/{lp_id}/reject", headers=superuser_token_headers, json={"comment": "格式不符"})
        assert rj.status_code == 200 and rj.json()["status"] == "rejected"
        rs = client.post(f"{API}/lesson-plans/{lp_id}/resubmit", headers=teacher_token_headers)
        assert rs.status_code == 200 and rs.json()["status"] == "pending"

    def test_publish_to_kb_requires_approved(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：已通过审核的教案入知识库（生成版本快照）；教师无权限 → 403"""
        lp_id = self._draft(client, teacher_token_headers)
        # 未审核直接入库应失败（仅 approved 可入库）
        bad = client.post(f"{API}/lesson-plans/{lp_id}/publish-to-kb", headers=superuser_token_headers)
        assert bad.status_code in (400, 403)
        # 教师无 kb_manage 权限
        t_bad = client.post(f"{API}/lesson-plans/{lp_id}/publish-to-kb", headers=teacher_token_headers)
        assert t_bad.status_code == 403
        # 走完整流程后入库
        client.post(f"{API}/lesson-plans/{lp_id}/submit", headers=teacher_token_headers)
        client.post(f"{API}/lesson-plans/{lp_id}/approve", headers=superuser_token_headers)
        ok = client.post(f"{API}/lesson-plans/{lp_id}/publish-to-kb", headers=superuser_token_headers)
        assert ok.status_code == 200, ok.text
        assert ok.json()["snapshot"]["version"] >= 1

    def test_submit_wrong_status(self, client, teacher_token_headers, superuser_token_headers):
        """❌ 错误：已归档教案不能再次提交 → 400"""
        lp_id = self._draft(client, teacher_token_headers)
        client.post(f"{API}/lesson-plans/{lp_id}/submit", headers=teacher_token_headers)
        client.post(f"{API}/lesson-plans/{lp_id}/approve", headers=superuser_token_headers)
        client.post(f"{API}/lesson-plans/{lp_id}/archive", headers=superuser_token_headers)
        r = client.post(f"{API}/lesson-plans/{lp_id}/submit", headers=teacher_token_headers)
        assert r.status_code == 400
