# -*- coding: utf-8 -*-
"""L1 接口功能测试：utils（健康检查 + 测试邮件，纯 DB/SMTP）。"""
from __future__ import annotations

import pytest
from unittest.mock import patch

import app.api.routes.utils as utils_rt

API = "/api/v1"


class TestHealth:
    def test_health_check(self, client):
        """✅ 正常：健康检查（无需鉴权）返回 true"""
        r = client.get(f"{API}/utils/health-check/")
        assert r.status_code == 200
        assert r.json() is True


class TestTestEmail:
    def test_requires_superuser(self, client, teacher_token_headers):
        """❌ 错误：普通教师调用测试邮件 → 403（仅超管）"""
        r = client.post(f"{API}/utils/test-email/?email_to=foo@bar.com", headers=teacher_token_headers)
        assert r.status_code == 403

    def test_send_email_success(self, client, superuser_token_headers):
        """✅ 正常：超管触发测试邮件（SMTP 被 mock 不真正发送）"""
        with patch.object(utils_rt, "send_email") as m:
            r = client.post(f"{API}/utils/test-email/?email_to=foo@bar.com", headers=superuser_token_headers)
            assert r.status_code == 201, r.text
            assert r.json().get("message") == "Test email sent"
            assert m.called
