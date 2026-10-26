# -*- coding: utf-8 -*-
"""L1 接口功能测试：管理员后台（admin，DB + 图谱审核分发）。

覆盖：候选知识点队列 / 教师建议工单 / 统计看板 / 系统日志；
含 403（仅超管）/ 404 / 批量审核 / 空选校验。
"""
from __future__ import annotations

import pytest

from tests.api.l1.helpers import submit_candidate, submit_suggestion

API = "/api/v1"


class TestCandidates:
    def test_submit_and_list(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：教师提交候选 → 超管可见（pending）"""
        c = submit_candidate(client, teacher_token_headers, name="候选质点")
        assert c.status_code == 200, c.text
        cid = c.json()["id"]
        lst = client.get(f"{API}/admin/candidates", headers=superuser_token_headers)
        assert lst.status_code == 200
        assert any(x["id"] == cid for x in lst.json()["data"])

    def test_teacher_cannot_list_candidates(self, client, teacher_token_headers):
        """❌ 错误：普通教师访问管理队列 → 403"""
        r = client.get(f"{API}/admin/candidates", headers=teacher_token_headers)
        assert r.status_code == 403

    def test_approve_writes_graph(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：审核通过候选（图谱分发桩）-> 状态 approved"""
        c = submit_candidate(client, teacher_token_headers, name="候选导数")
        cid = c.json()["id"]
        a = client.post(f"{API}/admin/candidates/{cid}/approve", headers=superuser_token_headers)
        assert a.status_code == 200, a.text
        lst = client.get(f"{API}/admin/candidates?status=approved", headers=superuser_token_headers)
        assert any(x["id"] == cid for x in lst.json()["data"])

    def test_reject_candidate(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：驳回候选 -> rejected"""
        c = submit_candidate(client, teacher_token_headers, name="候选向量")
        cid = c.json()["id"]
        r = client.post(f"{API}/admin/candidates/{cid}/reject", headers=superuser_token_headers)
        assert r.status_code == 200 and r.json()["message"] == "已驳回"

    def test_approve_missing(self, client, superuser_token_headers):
        """❌ 错误：审批不存在候选 -> 404"""
        r = client.post(f"{API}/admin/candidates/00000000-0000-0000-0000-000000000000/approve", headers=superuser_token_headers)
        assert r.status_code == 404

    def test_batch_approve_requires_selection(self, client, superuser_token_headers):
        """🈳 空白值：批量审核未选任何项 -> 400"""
        r = client.post(f"{API}/admin/candidates/batch-approve", headers=superuser_token_headers, json={"ids": []})
        assert r.status_code == 400

    def test_batch_approve_empty_list(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：批量审批（含一条已提交候选）"""
        c = submit_candidate(client, teacher_token_headers, name="批量候选")
        cid = c.json()["id"]
        r = client.post(f"{API}/admin/candidates/batch-approve", headers=superuser_token_headers, json={"ids": [cid]})
        assert r.status_code == 200, r.text
        assert r.json()["approved_count"] >= 1


class TestSuggestions:
    def test_submit_list_mine(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：教师提建议 -> 本人可见；超管可列全部"""
        s = submit_suggestion(client, teacher_token_headers, name="建议知识点A")
        assert s.status_code == 200
        sid = s.json()["id"]
        mine = client.get(f"{API}/admin/suggestions/mine", headers=teacher_token_headers)
        assert any(x["id"] == sid for x in mine.json()["data"])
        allm = client.get(f"{API}/admin/suggestions", headers=superuser_token_headers)
        assert any(x["id"] == sid for x in allm.json()["data"])

    def test_teacher_cannot_list_all_suggestions(self, client, teacher_token_headers):
        """❌ 错误：教师访问全部建议队列 -> 403"""
        r = client.get(f"{API}/admin/suggestions", headers=teacher_token_headers)
        assert r.status_code == 403

    def test_approve_and_reject_suggestion(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：建议工单审核通过 / 待处理建议驳回"""
        s = submit_suggestion(client, teacher_token_headers, name="建议知识点B")
        sid = s.json()["id"]
        a = client.post(f"{API}/admin/suggestions/{sid}/approve", headers=superuser_token_headers)
        assert a.status_code == 200
        # 驳回一条「待处理」建议（正常路径）
        s2 = submit_suggestion(client, teacher_token_headers, name="建议知识点C")
        sid2 = s2.json()["id"]
        rj = client.post(f"{API}/admin/suggestions/{sid2}/reject", headers=superuser_token_headers)
        assert rj.status_code == 200 and rj.json()["message"] == "已驳回"

    def test_reject_approved_suggestion_should_400(self, client, teacher_token_headers, superuser_token_headers):
        """❌ 错误：已审核通过的工单再次驳回应 400（reject 已补「已处理」守卫）"""
        s = submit_suggestion(client, teacher_token_headers, name="建议知识点D")
        sid = s.json()["id"]
        client.post(f"{API}/admin/suggestions/{sid}/approve", headers=superuser_token_headers)
        rj = client.post(f"{API}/admin/suggestions/{sid}/reject", headers=superuser_token_headers)
        assert rj.status_code == 400


class TestStatsAndLogs:
    def test_stats_superuser_only(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：超管获取统计看板（图谱计数由桩返回 0）；教师 -> 403"""
        r = client.get(f"{API}/admin/stats", headers=superuser_token_headers)
        assert r.status_code == 200
        body = r.json()
        for k in ("pending_candidates", "subjects_count", "documents_total",
                 "documents_processing", "documents_failed", "knowledge_points_count"):
            assert k in body
        assert client.get(f"{API}/admin/stats", headers=teacher_token_headers).status_code == 403

    def test_logs(self, client, teacher_token_headers, superuser_token_headers):
        """✅ 正常：系统日志列表（提交候选会产生日志）"""
        submit_candidate(client, teacher_token_headers, name="日志候选")
        r = client.get(f"{API}/admin/logs", headers=superuser_token_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_graph_quality_check(self, client, superuser_token_headers):
        """✅ 正常：图谱质量检测（桩返回空结构）"""
        r = client.get(f"{API}/admin/graph-quality", headers=superuser_token_headers)
        assert r.status_code == 200
        body = r.json()
        assert "loops" in body and "orphans" in body
