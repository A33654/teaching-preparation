# -*- coding: utf-8 -*-
"""通过真实 HTTP 接口造数的便捷函数（L1 集成测试用）。

所有函数返回 requests.Response，调用方自行断言 status_code 与 json()。
统一使用 /api/v1 前缀。
"""
from __future__ import annotations

import uuid
from io import BytesIO

API = "/api/v1"


def _uid() -> str:
    """短随机后缀，规避共享内存库中的 UNIQUE 约束（同名资源跨用例累积）。"""
    return uuid.uuid4().hex[:8]


# ===================== 课程表 / 学科 =====================

def create_subject(client, headers, name=None) -> "object":
    name = name or f"学科-{_uid()}"
    return client.post(f"{API}/curriculum/subjects", headers=headers, json={"name": name})


def create_textbook(client, headers, subject_id, name=None) -> "object":
    name = name or f"教材-{_uid()}"
    return client.post(
        f"{API}/curriculum/textbooks",
        headers=headers,
        json={"name": name, "subject_id": str(subject_id)},
    )


def create_chapter(client, headers, textbook_id, title=None, level=1, parent_id=None) -> "object":
    title = title or f"章节-{_uid()}"
    payload = {"title": title, "textbook_id": str(textbook_id), "level": level}
    if parent_id is not None:
        payload["parent_id"] = str(parent_id)
    return client.post(f"{API}/curriculum/chapters", headers=headers, json=payload)


# ===================== 文档 =====================

def upload_document(client, headers, text="二次函数是形如 f(x)=ax^2+bx+c 的函数，图像为抛物线。" * 5,
                    filename="test.txt", auto_analyze=False) -> "object":
    files = {"file": (filename, BytesIO(text.encode("utf-8")), "text/plain")}
    return client.post(
        f"{API}/documents/upload",
        headers=headers,
        files=files,
        params={"auto_analyze": "false" if not auto_analyze else "true"},
    )


# ===================== 教案 =====================

def create_lesson_plan(client, headers, title=None, subject="数学",
                       teaching_objectives="理解函数概念。",
                       teaching_process="1.导入 2.新授") -> "object":
    title = title or f"教案-{_uid()}"
    return client.post(
        f"{API}/lesson-plans/",
        headers=headers,
        json={
            "title": title,
            "subject": subject,
            "teaching_objectives": teaching_objectives,
            "teaching_process": teaching_process,
        },
    )


# ===================== 候选知识点 / 建议工单 =====================

def submit_candidate(client, headers, name=None, subject="数学", kind="llm_extraction") -> "object":
    name = name or f"候选-{_uid()}"
    return client.post(
        f"{API}/admin/candidates",
        headers=headers,
        json={"name": name, "subject": subject, "kind": kind},
    )


def submit_suggestion(client, headers, name=None, subject="数学", kind="missing_kp") -> "object":
    name = name or f"建议-{_uid()}"
    return client.post(
        f"{API}/admin/suggestions",
        headers=headers,
        json={"name": name, "subject": subject, "kind": kind},
    )
