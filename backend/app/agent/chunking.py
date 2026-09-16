"""文档分块：优先按章节结构，回退按段落滑动窗口。"""
import re

# 章节分隔模式（中英文标题）
_HEADING_PATTERN = re.compile(
    r"(?:^|\n)\s*"
    r"(?:"
    r"第[一二三四五六七八九十\d]+[章节]|"  # 第X章、第X节
    r"Chapter\s+\d+|"                     # Chapter 1
    r"#{1,3}\s+|"                         # Markdown 标题
    r"[一二三四五六七八九十]、|"           # 一、二、
    r"\d+[\.\、]"                         # 1. 2.
    r")"
    r"\s*[^\n]*",
    re.MULTILINE,
)


def chunk_document(text: str, max_chunk: int = 2000, overlap: int = 100) -> list[dict]:
    """把文档切成块，返回 [{"title": str, "content": str, "index": int}]"""
    chunks: list[dict] = []

    # 1. 按章节标题切分
    parts = _HEADING_PATTERN.split(text)
    titles = _HEADING_PATTERN.findall(text)

    if titles:
        if parts[0].strip():
            chunks.append({"title": "前言", "content": parts[0].strip(), "index": 0})
        for i, title in enumerate(titles):
            content = (
                parts[i + 1].strip() if i + 1 < len(parts) else ""
            )
            if content or title.strip():
                chunks.append(
                    {
                        "title": title.strip().lstrip("#").strip()[:100],
                        "content": content,
                        "index": len(chunks),
                    }
                )

    # 2. 无标题或全部为空时，按段落组回退
    if not chunks:
        paragraphs = [
            p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()
        ]
        for i in range(0, len(paragraphs), 3):
            chunk_text = "\n\n".join(paragraphs[i : i + 3])
            chunks.append(
                {"title": f"段落 {i // 3 + 1}", "content": chunk_text, "index": len(chunks)}
            )

    # 3. 超长块二次切分（按句子 + 重叠）
    final_chunks: list[dict] = []
    for chunk in chunks:
        content = chunk["content"]
        if len(content) <= max_chunk:
            final_chunks.append(chunk)
            continue
        sentences = re.split(r"(?<=[。！？；.!?;])\s*", content)
        current = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) > max_chunk and current:
                final_chunks.append(
                    {"title": chunk["title"], "content": current, "index": len(final_chunks)}
                )
                current = current[-overlap:] if len(current) > overlap else current
            current += sent
        if current.strip():
            final_chunks.append(
                {"title": chunk["title"], "content": current.strip(), "index": len(final_chunks)}
            )

    return final_chunks
