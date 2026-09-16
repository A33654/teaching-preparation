"""文件解析器：从 PDF / DOCX / TXT 提取文本"""

import io
from pathlib import Path


def extract_text(file_path: str, file_type: str) -> str:
    """根据文件类型提取文本，解析失败时尝试当作纯文本"""
    # 标准化文件类型
    ft = file_type.lower().lstrip(".")
    try:
        if ft == "txt":
            return _extract_txt(file_path)
        elif ft in ("pdf",):
            return _extract_pdf(file_path)
        elif ft in ("docx", "doc"):
            return _extract_docx(file_path)
        else:
            # 未知类型，尝试当作文本
            return _extract_txt(file_path)
    except (ImportError, Exception):
        # 解析失败时回退为纯文本读取
        return _extract_txt(file_path)


def _extract_txt(file_path: str) -> str:
    """提取纯文本"""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _extract_pdf(file_path: str) -> str:
    """提取 PDF 文本（优先用 pdfplumber，回退到 pymupdf）"""
    try:
        import pdfplumber

        texts: list[str] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
        return "\n\n".join(texts)
    except ImportError:
        pass

    try:
        import fitz  # pymupdf

        texts: list[str] = []
        doc = fitz.open(file_path)
        for page in doc:
            text = page.get_text()
            if text:
                texts.append(text)
        doc.close()
        return "\n\n".join(texts)
    except ImportError:
        raise ImportError(
            "需要安装 pdfplumber 或 pymupdf 来解析 PDF 文件。"
            "运行: uv add pdfplumber"
        )


def _extract_docx(file_path: str) -> str:
    """提取 Word 文档文本"""
    try:
        from docx import Document

        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except ImportError:
        raise ImportError(
            "需要安装 python-docx 来解析 Word 文件。"
            "运行: uv add python-docx"
        )


def chunk_text(text: str, max_chunk_size: int = 2000) -> list[dict]:
    """
    将文本按段落分块，每块尽量不超过 max_chunk_size 字符。
    返回 list[{"index": int, "content": str}]
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[dict] = []
    current_chunk = ""
    chunk_index = 0

    for para in paragraphs:
        if len(current_chunk) + len(para) > max_chunk_size and current_chunk:
            chunks.append({"index": chunk_index, "content": current_chunk.strip()})
            chunk_index += 1
            current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append({"index": chunk_index, "content": current_chunk.strip()})

    return chunks
