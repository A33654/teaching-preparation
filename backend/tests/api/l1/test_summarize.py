# -*- coding: utf-8 -*-
"""L1 接口功能测试：文件概括 + PPT 生成（summarize，LangGraph 桩 + python-pptx 渲染 + DB 记录）。

覆盖：文生 PPT / 文件生 PPT / 概括 / PPT 列表详情导出保存；含 401 / 400 边界。
"""
from __future__ import annotations

from io import BytesIO

API = "/api/v1"

SAMPLE_TEXT = "二次函数是形如 y=ax^2+bx+c 的函数，图像为抛物线，顶点在对称轴上，开口方向由 a 决定。" * 8


class TestGeneratePptFromText:
    def test_generate_from_text(self, client, teacher_token_headers):
        """✅ 正常：文本直接生成 PPT（返回 pptx 流，并记录 PptRecord）"""
        r = client.post(
            f"{API}/summarize/generate-ppt-from-text",
            headers=teacher_token_headers,
            json={"title": "二次函数的图像", "text": SAMPLE_TEXT, "style": "professional", "slide_count": 6},
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/vnd.openxmlformats")

    def test_short_text_rejected(self, client, teacher_token_headers):
        """🈳 空白值：文本过短（<10）-> 400"""
        r = client.post(
            f"{API}/summarize/generate-ppt-from-text",
            headers=teacher_token_headers,
            json={"title": "x", "text": "太短", "style": "professional"},
        )
        assert r.status_code == 400

    def test_no_auth(self, client):
        """❌ 错误：未登录 -> 401"""
        r = client.post(f"{API}/summarize/generate-ppt-from-text", json={"title": "x", "text": SAMPLE_TEXT})
        assert r.status_code == 401


class TestGeneratePptFromFile:
    def test_generate_from_file(self, client, teacher_token_headers):
        """✅ 正常：上传 txt 生成 PPT"""
        files = {"file": ("素材.txt", BytesIO(SAMPLE_TEXT.encode("utf-8")), "text/plain")}
        r = client.post(
            f"{API}/summarize/generate-ppt",
            headers=teacher_token_headers,
            files=files,
            params={"style": "vivid", "slide_count": 4},
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/vnd.openxmlformats")


class TestSummarize:
    def test_summarize_file(self, client, teacher_token_headers):
        """✅ 正常：上传文件概括（LangGraph 桩）返回 summary/key_topics/suggested_approach"""
        files = {"file": ("概括.txt", BytesIO(SAMPLE_TEXT.encode("utf-8")), "text/plain")}
        r = client.post(f"{API}/summarize/", headers=teacher_token_headers, files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("summary", "key_topics", "suggested_approach"):
            assert k in body


class TestPptRecords:
    def _make_ppt(self, client, headers):
        r = client.post(
            f"{API}/summarize/generate-ppt-from-text",
            headers=headers,
            json={"title": "记录测试", "text": SAMPLE_TEXT, "style": "minimal", "slide_count": 5},
        )
        return r

    def test_list_detail_export_save(self, client, teacher_token_headers):
        """✅ 正常：生成后列表可见 -> 详情可取 -> 导出文件 -> 保存重新生成"""
        self._make_ppt(client, teacher_token_headers)
        lst = client.get(f"{API}/summarize/ppt-list", headers=teacher_token_headers)
        assert lst.status_code == 200
        records = lst.json()["data"]
        assert records, "应至少有一条 PPT 记录"
        pid = records[0]["id"]

        det = client.get(f"{API}/summarize/ppt/{pid}", headers=teacher_token_headers)
        assert det.status_code == 200 and det.json()["id"] == pid

        exp = client.get(f"{API}/summarize/ppt/{pid}/export", headers=teacher_token_headers)
        assert exp.status_code == 200
        assert exp.headers["content-type"].startswith("application/vnd.openxmlformats")

        save = client.put(
            f"{API}/summarize/ppt/{pid}/save",
            headers=teacher_token_headers,
            json={"slides": [{"title": "封面", "bullets": ["要点1"]}], "style": "professional"},
        )
        assert save.status_code == 200, save.text
        assert save.headers["content-type"].startswith("application/vnd.openxmlformats")

    def test_detail_missing(self, client, teacher_token_headers):
        """❌ 错误：不存在 PPT -> 404"""
        r = client.get(f"{API}/summarize/ppt/00000000-0000-0000-0000-000000000000", headers=teacher_token_headers)
        assert r.status_code == 404

    def test_detail_invalid_uuid(self, client, teacher_token_headers):
        """❌ 错误：非法 UUID -> 400"""
        r = client.get(f"{API}/summarize/ppt/not-uuid", headers=teacher_token_headers)
        assert r.status_code == 400
