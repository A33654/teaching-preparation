# -*- coding: utf-8 -*-
"""L1 接口功能测试：AI 教学助手问答（chat，LangGraph ReAct Agent，SSE/JSON 双模式）。

覆盖：空消息守卫（错误/边界）/ 正常问答（LLM 桩）/ SSE 与 JSON 两种模式。
"""
from __future__ import annotations

import json

API = "/api/v1"


class TestChatGuard:
    def test_empty_message_json(self, client, teacher_token_headers):
        """🈳 空白值：空消息（json 模式）返回提示而非崩溃"""
        r = client.post(f"{API}/chat/", headers=teacher_token_headers, json={"message": "  ", "mode": "json"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reply"] == "请输入问题" and body["sources"] == []

    def test_empty_message_sse(self, client, teacher_token_headers):
        """🈳 空白值：空消息（sse 模式）返回 error 事件流"""
        r = client.post(f"{API}/chat/", headers=teacher_token_headers, json={"message": "", "mode": "sse"})
        assert r.status_code == 200
        assert '"type": "error"' in r.text


class TestChatFlow:
    def test_json_mode_answer(self, client, teacher_token_headers):
        """✅ 正常：非空消息（json 模式，LLM 桩）返回聚合后的回复"""
        r = client.post(f"{API}/chat/", headers=teacher_token_headers,
                        json={"message": "二次函数是什么？", "mode": "json"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reply"] and "二次函数" in body["reply"]
        assert isinstance(body["sources"], list)

    def test_sse_mode_stream(self, client, teacher_token_headers):
        """✅ 正常：非空消息（sse 模式，LLM 桩）返回 token/done 事件流"""
        r = client.post(f"{API}/chat/", headers=teacher_token_headers,
                        json={"message": "讲讲导数", "mode": "sse"})
        assert r.status_code == 200
        assert "data:" in r.text
        # 至少应含一个 token 与一个 done 事件
        has_token = '"type": "token"' in r.text
        has_done = '"type": "done"' in r.text
        assert has_token and has_done
