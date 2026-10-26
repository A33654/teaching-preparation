# -*- coding: utf-8 -*-
"""L1 接口功能测试：课程表 + 学习任务（reminders，纯 DB 业务）。

覆盖：正常 / 空白值 / 错误 / 边界；含权限校验（未登录 401、越权 404）。
"""
from __future__ import annotations

import pytest

API = "/api/v1"


# ===================== 课程表 =====================
class TestSchedules:
    def test_create_and_list(self, client, teacher_token_headers):
        """✅ 正常：创建课程表项并出现在列表"""
        r = client.post(
            f"{API}/reminders/schedules",
            headers=teacher_token_headers,
            json={"day_of_week": 0, "start_time": "08:00", "end_time": "08:45", "subject": "数学"},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        lst = client.get(f"{API}/reminders/schedules", headers=teacher_token_headers)
        assert lst.status_code == 200
        ids = [s["id"] for s in lst.json()["data"]]
        assert sid in ids

    def test_create_boundary_day(self, client, teacher_token_headers):
        """⚠️ 边界：day_of_week=6（周日）合法；=7 应被校验拒绝（422）"""
        ok = client.post(
            f"{API}/reminders/schedules",
            headers=teacher_token_headers,
            json={"day_of_week": 6, "start_time": "09:00", "end_time": "09:45", "subject": "语文"},
        )
        assert ok.status_code == 200
        bad = client.post(
            f"{API}/reminders/schedules",
            headers=teacher_token_headers,
            json={"day_of_week": 7, "start_time": "09:00", "end_time": "09:45", "subject": "语文"},
        )
        assert bad.status_code == 422

    def test_create_empty_subject(self, client, teacher_token_headers):
        """🈳 空白值：subject 为空串应被校验拒绝（422）—— ScheduleCreate.subject 已加 min_length=1"""
        r = client.post(
            f"{API}/reminders/schedules",
            headers=teacher_token_headers,
            json={"day_of_week": 1, "start_time": "10:00", "end_time": "10:45", "subject": ""},
        )
        assert r.status_code == 422

    def test_delete_invalid_and_missing(self, client, teacher_token_headers):
        """❌ 错误：非法 UUID → 400；不存在 → 404"""
        bad = client.delete(f"{API}/reminders/schedules/not-a-uuid", headers=teacher_token_headers)
        assert bad.status_code == 400
        missing = client.delete(f"{API}/reminders/schedules/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers)
        assert missing.status_code == 404

    def test_delete_success(self, client, teacher_token_headers):
        """✅ 正常：删除自己的课程表项"""
        c = client.post(
            f"{API}/reminders/schedules",
            headers=teacher_token_headers,
            json={"day_of_week": 2, "start_time": "11:00", "end_time": "11:45", "subject": "英语"},
        )
        sid = c.json()["id"]
        d = client.delete(f"{API}/reminders/schedules/{sid}", headers=teacher_token_headers)
        assert d.status_code == 200
        assert d.json()["message"] == "deleted"


# ===================== 学习任务 =====================
class TestTasks:
    def test_create_toggle_delete(self, client, teacher_token_headers):
        """✅ 正常：创建→切换完成→删除"""
        c = client.post(
            f"{API}/reminders/tasks",
            headers=teacher_token_headers,
            json={"title": "批改作业", "due_date": "2026-02-01", "priority": "high"},
        )
        assert c.status_code == 200
        tid = c.json()["id"]
        # 列表默认隐藏已完成
        tgl = client.put(f"{API}/reminders/tasks/{tid}/toggle", headers=teacher_token_headers)
        assert tgl.status_code == 200
        assert tgl.json()["completed"] is True
        # 切换回来
        client.put(f"{API}/reminders/tasks/{tid}/toggle", headers=teacher_token_headers)
        d = client.delete(f"{API}/reminders/tasks/{tid}", headers=teacher_token_headers)
        assert d.status_code == 200

    def test_list_show_completed(self, client, teacher_token_headers):
        """✅ 正常：show_completed=true 能看到已完成的任务"""
        c = client.post(
            f"{API}/reminders/tasks", headers=teacher_token_headers,
            json={"title": "备教案", "due_date": "2026-02-02"},
        )
        tid = c.json()["id"]
        client.put(f"{API}/reminders/tasks/{tid}/toggle", headers=teacher_token_headers)
        lst = client.get(f"{API}/reminders/tasks?show_completed=true", headers=teacher_token_headers)
        ids = [t["id"] for t in lst.json()["data"]]
        assert tid in ids

    def test_toggle_missing(self, client, teacher_token_headers):
        """❌ 错误：切换不存在任务 → 404"""
        r = client.put(f"{API}/reminders/tasks/00000000-0000-0000-0000-000000000000/toggle", headers=teacher_token_headers)
        assert r.status_code == 404

    def test_toggle_invalid_uuid(self, client, teacher_token_headers):
        """❌ 错误：非法 UUID → 400"""
        r = client.put(f"{API}/reminders/tasks/abc/toggle", headers=teacher_token_headers)
        assert r.status_code == 400

    def test_create_empty_title(self, client, teacher_token_headers):
        """🈳 空白值：title 缺省/空串应被校验拒绝（422）—— TaskCreate.title 已加 min_length=1"""
        r = client.post(f"{API}/reminders/tasks", headers=teacher_token_headers, json={"title": ""})
        assert r.status_code == 422


# ===================== 今日概览 + 权限 =====================
class TestOverviewAndAuth:
    def test_today_overview(self, client, teacher_token_headers):
        """✅ 正常：今日概览返回结构（schedule + tasks + day_name）"""
        r = client.get(f"{API}/reminders/today", headers=teacher_token_headers)
        assert r.status_code == 200
        body = r.json()
        assert "today_schedule" in body and "upcoming_tasks" in body and "day_name" in body

    def test_no_auth_returns_401(self, client):
        """❌ 错误：未带令牌访问受保护接口 → 401"""
        r = client.get(f"{API}/reminders/schedules")
        assert r.status_code == 401
