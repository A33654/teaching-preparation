"""文档检索工具（独立封装）。"""
import json
from typing import Callable

from langchain_core.tools import tool
from sqlmodel import Session, col, select

from app.models import Document


def build_document_tools(owner_id: str, session: Session) -> list[Callable]:
    """构建文档检索工具（按用户绑定数据权限）"""

    @tool
    def search_documents(query: str, top_k: int = 5) -> str:
        """在用户已上传的文档内容中全文检索。

        【调用时机】问题涉及教材原文、讲义内容、已上传文档的具体表述时调用；
        知识点概念与关系类问题应优先使用知识图谱工具。
        【输入】query 为关键词或问题原文。
        """
        docs = session.exec(
            select(Document).where(
                Document.owner_id == owner_id,
                col(Document.extracted_text).is_not(None),
            )
        ).all()
        hits = []
        q = query.lower()
        for doc in docs:
            text = doc.extracted_text or ""
            if not text:
                continue
            pos = text.lower().find(q)
            score = 0
            if pos >= 0:
                score = 1.0
            elif any(kw in text for kw in q.split() if len(kw) >= 2):
                score = 0.5
            if score > 0:
                start = max(0, pos - 100) if pos >= 0 else 0
                snippet = text[start : start + 400].replace("\n", " ")
                hits.append(
                    {
                        "document_id": str(doc.id),
                        "filename": doc.original_filename,
                        "snippet": snippet,
                        "score": score,
                    }
                )
        hits.sort(key=lambda h: -h["score"])
        hits = hits[:top_k]
        sources = [
            {"type": "document", "name": h["filename"], "id": h["document_id"]}
            for h in hits
        ]
        return json.dumps({"result": hits, "sources": sources}, ensure_ascii=False)

    return [search_documents]
