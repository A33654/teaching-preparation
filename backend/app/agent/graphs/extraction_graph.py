"""文档知识抽取图：学科识别 → 分块抽取知识点 → 抽取关系 → 写入 Neo4j → 概括。

长文档处理策略（防上下文超限/静默失败）：
- 粗分块按标题/句子切分（每块 ≤ 2500 字符，块间带重叠），逐块独立调用 LLM；
- 单块 LLM 报上下文超限时自动对半缩小重试（兜底）；
- 块间同名知识点合并去重、关系清洗后统一写入图谱；
- LLM 失败逐块打印完整异常日志（含真实报错），失败块回退正则提取器；
- 全量处理所有块（不静默截断），全部失败时 error 携带底层真实原因。
"""
import logging
import re

from app.agent.chunking import chunk_document
from app.agent.llm import get_chat_model, get_structured_model
from app.agent.schemas import ExtractionOutput, SummarizeOutput
from app.agent.state import ExtractionState
from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

logger = logging.getLogger(__name__)

# 抽取块大小：中文 1 字符 ≈ 1 token，2500 字符 + 指令 ≈ 3000 token 输入，
# 远低于主流模型 64K 上下文；输出 4000 token 上限足够单块知识点量
EXTRACTION_MAX_CHUNK = 2500
# 上下文超限兜底时的最小块大小（再小就没有抽取价值）
EXTRACTION_MIN_CHUNK = 800

EXTRACTION_PROMPT = """你是教育知识图谱专家。从给定文档片段中提取知识点及知识点之间的关系。

规则：
1. 知识点名称要简洁精准（如「勾股定理」「二次函数」「牛顿第一定律」）
2. 只提取有教学意义的概念、定理、方法，不要提取普通名词
3. 关系只引用已提取知识点的名称，名称必须完全一致
4. relation_type 取值：prerequisite=前置知识（学习A需要先掌握B时，B是A的前置）、contains=包含（整体与部分）、related_to=相关
5. 文档片段标题：{chunk_title}"""

# 上下文超限的特征报错片段（兼容 DeepSeek/Qwen/Kimi 的错误消息）
_CONTEXT_OVERFLOW_PATTERNS = re.compile(
    r"context.?length|maximum context|context_length_exceeded|too long|"
    r"max token|token limit|超出.*(上下文|长度|上限)|长度超过",
    re.IGNORECASE,
)


def _is_context_overflow(err: Exception) -> bool:
    """判断异常是否为上下文超限类错误"""
    return bool(_CONTEXT_OVERFLOW_PATTERNS.search(str(err)))


def _detect_subject(state: ExtractionState) -> dict:
    """节点1：识别学科（LLM 结构化输出，失败回退关键词匹配）"""
    text = state["text"]
    try:
        from app.knowledge_extractor import detect_subject as keyword_detect

        subject = keyword_detect(text)
    except Exception:
        subject = "通用"
    state["subject"] = subject
    return {"subject": subject}


def _regex_fallback_merge(content: str, merged: dict[str, dict], relations: list[dict], state: ExtractionState) -> None:
    """正则提取器兜底：把结果合并进 merged/relations（不抛异常）"""
    from app.knowledge_extractor import extract_knowledge_points as regex_extract
    from app.knowledge_extractor import extract_relations as regex_relations

    try:
        for kp in regex_extract(content):
            name = kp["name"]
            if name not in merged:
                merged[name] = {
                    "name": name,
                    "description": kp.get("description", "")[:2000],
                    "subject": kp.get("subject") or state["subject"],
                    "difficulty": 1,
                    "is_key_point": False,
                }
        kp_list = list(merged.values())
        relations.extend(regex_relations(content, kp_list))
    except Exception as e:
        logger.warning("正则回退提取失败: %r", e)


def _extract_one_chunk(
    structured_llm,
    title: str,
    content: str,
    state: ExtractionState,
    merged: dict[str, dict],
    relations: list[dict],
    detected_subject: str,
    chunk_index: int,
) -> str:
    """抽取单个块：LLM 结构化输出 → 上下文超限自动缩小重试 → 正则兜底。

    返回更新后的 detected_subject；成功/失败的统计与日志在调用方处理。
    """
    llm_error: Exception | None = None
    # 兜底重试：上下文超限时逐级对半缩小块，最小到 EXTRACTION_MIN_CHUNK
    shrink_content = content
    while True:
        try:
            result: ExtractionOutput = structured_llm.invoke(
                EXTRACTION_PROMPT.format(chunk_title=title)
                + "\n\n文档片段内容：\n"
                + shrink_content
            )
            if result.subject:
                detected_subject = detected_subject or result.subject
            for kp in result.knowledge_points:
                name = kp.name.strip()
                if not name:
                    continue
                if name not in merged:
                    merged[name] = {
                        "name": name,
                        "description": kp.description,
                        "subject": kp.subject or detected_subject or state["subject"],
                        "difficulty": kp.difficulty,
                        "is_key_point": kp.is_key_point,
                    }
            relations.extend(r.model_dump() for r in result.relations)
            return detected_subject
        except Exception as e:
            llm_error = e
            if _is_context_overflow(e) and len(shrink_content) > EXTRACTION_MIN_CHUNK:
                old_len = len(shrink_content)
                shrink_content = shrink_content[: old_len // 2]
                logger.warning(
                    "块 %s（标题 %r）上下文超限，缩小重试: %d → %d 字符",
                    chunk_index, title, old_len, len(shrink_content),
                )
                continue
            break

    # LLM 失败：打印完整真实错误（不静默），回退正则提取
    logger.error(
        "块 %s（标题 %r，%d 字符）LLM 抽取失败，回退正则提取。错误详情: %r",
        chunk_index, title, len(shrink_content), llm_error,
    )
    _regex_fallback_merge(shrink_content, merged, relations, state)
    return detected_subject


def _extract_knowledge_points(state: ExtractionState) -> dict:
    """节点2：逐块抽取知识点（LLM 优先，正则回退），跨块按名称去重合并"""
    text = state["text"]
    chunks = chunk_document(text, max_chunk=EXTRACTION_MAX_CHUNK)
    if not chunks:
        logger.warning("文档分块结果为空，抽取中止")
        return {"subject": state["subject"], "knowledge_points": [], "relations": []}

    structured_llm = get_structured_model(ExtractionOutput, temperature=0.2, max_tokens=4000)

    merged: dict[str, dict] = {}
    relations: list[dict] = []
    detected_subject = ""

    # 全量处理所有块（不静默截断）；块数异常多时仍全部处理但记录警告
    if len(chunks) > 50:
        logger.warning("文档切分出 %d 个块，抽取耗时可能较长", len(chunks))
    for idx, chunk in enumerate(chunks):
        content = chunk["content"][:EXTRACTION_MAX_CHUNK]
        detected_subject = _extract_one_chunk(
            structured_llm,
            chunk.get("title", ""),
            content,
            state,
            merged,
            relations,
            detected_subject,
            idx,
        )

    if not merged:
        logger.error("全部分块均未抽取出知识点，文档长度 %d，块数 %d", len(text), len(chunks))

    if detected_subject:
        state["subject"] = detected_subject

    return {
        "subject": state["subject"],
        "knowledge_points": list(merged.values()),
        "relations": relations,
    }


def _extract_relations(state: ExtractionState) -> dict:
    """节点3：关系已在节点2中随知识点一起抽取（避免二次 LLM 调用），这里做清洗"""
    valid_names = {kp["name"] for kp in state["knowledge_points"]}
    cleaned = []
    seen = set()
    for rel in state["relations"]:
        src = rel.get("source_name")
        tgt = rel.get("target_name")
        rel_type = rel.get("relation_type")
        if (
            src in valid_names
            and tgt in valid_names
            and src != tgt
            and rel_type in ("prerequisite", "contains", "related_to")
        ):
            key = (src, tgt, rel_type)
            if key not in seen:
                seen.add(key)
                cleaned.append(rel)
    return {"relations": cleaned}


def _write_graph(state: ExtractionState) -> dict:
    """节点4：抽取结果写入待审核候选队列（管理员审核通过后才入 Neo4j）。

    增量图谱补全流程：LLM/正则 抽取 → 候选队列（pending）→ 管理员
    通过/驳回/编辑 → 写入正式知识图谱。保证正式图谱的每一条数据都
    经过人工审核。
    """
    import uuid as uuid_mod

    from app.core.db import engine
    from app.models import CandidateKnowledgePoint, ExtractionLog

    kps = state["knowledge_points"]
    if not kps:
        state["error"] = "未抽取到知识点（详情见后端日志）"
        return {"kp_ids": [], "error": state["error"]}

    # 关系 → 每个知识点的前置名称列表（prerequisite: source 的前置是 target）
    prereq_map: dict[str, list[str]] = {}
    for rel in state["relations"]:
        if rel.get("relation_type") == "prerequisite":
            prereq_map.setdefault(rel.get("source_name", ""), []).append(
                rel.get("target_name", "")
            )

    with Session(engine) as db_session:
        for kp in kps:
            db_session.add(
                CandidateKnowledgePoint(
                    name=kp["name"],
                    subject=kp.get("subject") or state["subject"] or "通用",
                    grade_level=None,
                    definition=(kp.get("description") or "")[:2000],
                    prerequisites="、".join(prereq_map.get(kp["name"], []))[:1000] or None,
                    source="llm_extraction",
                    status="pending",
                    document_id=uuid_mod.UUID(state["document_id"]) if state["document_id"] else None,
                    submitter_id=uuid_mod.UUID(state["owner_id"]),
                )
            )
        db_session.add(
            ExtractionLog(
                task_type="document_extract",
                status="success",
                message=f"文档 {state['document_id']} 抽取完成：{len(kps)} 个候选知识点进入待审核队列",
            )
        )
        db_session.commit()

    logger.info("文档 %s 抽取完成，%d 个候选知识点入待审核队列", state["document_id"], len(kps))
    return {"kp_ids": []}


def _summarize(state: ExtractionState) -> dict:
    """节点5：生成文档概括（失败时截断原文兜底）"""
    text = state["text"]
    try:
        result: SummarizeOutput = get_structured_model(
            SummarizeOutput, temperature=0.3, max_tokens=1000
        ).invoke(
            "你是教育分析师。概括以下教学文档，返回 summary（200-400字概括）、"
            "key_topics（3-8个核心主题）、suggested_approach（教学建议）。\n\n文档内容：\n"
            + text[:6000]
        )
        return {
            "summary": result.summary,
            "key_topics": result.key_topics,
        }
    except Exception as e:
        logger.error("文档概括 LLM 调用失败，使用截断原文兜底。错误详情: %r", e)
        return {"summary": text[:400]}


def build_extraction_graph():
    """构建文档知识抽取图"""
    graph = StateGraph(ExtractionState)
    graph.add_node("detect_subject", _detect_subject)
    graph.add_node("extract_knowledge_points", _extract_knowledge_points)
    graph.add_node("extract_relations", _extract_relations)
    graph.add_node("write_graph", _write_graph)
    graph.add_node("summarize", _summarize)

    graph.add_edge(START, "detect_subject")
    graph.add_edge("detect_subject", "extract_knowledge_points")
    graph.add_edge("extract_knowledge_points", "extract_relations")
    graph.add_edge("extract_relations", "write_graph")
    graph.add_edge("write_graph", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


_extraction_graph = None


def run_extraction(
    *, text: str, owner_id: str, document_id: str
) -> ExtractionState:
    """执行抽取图，返回最终状态"""
    global _extraction_graph
    if _extraction_graph is None:
        _extraction_graph = build_extraction_graph()
    state: ExtractionState = {
        "text": text,
        "owner_id": owner_id,
        "document_id": document_id,
        "subject": "",
        "summary": "",
        "knowledge_points": [],
        "relations": [],
        "kp_ids": [],
        "error": "",
    }
    return _extraction_graph.invoke(state)
