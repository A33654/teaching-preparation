"""文档概括图 + PPT 大纲生成图。

均为线性小图（当前单节点，预留评审/润色节点扩展位），
统一走 LangGraph 编排与结构化输出。
"""
from app.agent.llm import get_structured_model
from app.agent.schemas import PptOutlineOutput, SummarizeOutput
from app.agent.state import PptState, SummarizeState
from langgraph.graph import END, START, StateGraph


def _summarize_node(state: SummarizeState) -> dict:
    text = state["text"]
    result: SummarizeOutput = get_structured_model(
        SummarizeOutput, temperature=0.3, max_tokens=1500
    ).invoke(
        "你是教育分析师。分析以下教学文档，返回：summary（200-400字概括）、"
        "key_topics（3-8个核心主题）、suggested_approach（教学建议）。\n\n文档内容：\n"
        + text[:8000]
    )
    return {
        "summary": result.summary,
        "key_topics": result.key_topics,
        "suggested_approach": result.suggested_approach,
    }


def build_summarize_graph():
    graph = StateGraph(SummarizeState)
    graph.add_node("summarize", _summarize_node)
    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


_summarize_graph = None


def run_summarize(text: str) -> dict:
    """执行概括图，返回 {summary, key_topics, suggested_approach}"""
    global _summarize_graph
    if _summarize_graph is None:
        _summarize_graph = build_summarize_graph()
    try:
        result = _summarize_graph.invoke(
            {
                "text": text,
                "summary": "",
                "key_topics": [],
                "suggested_approach": "",
            }
        )
        return {
            "summary": result.get("summary", ""),
            "key_topics": result.get("key_topics", []),
            "suggested_approach": result.get("suggested_approach", ""),
        }
    except Exception:
        # LLM 不可用：截断原文兜底
        return {"summary": text[:500], "key_topics": [], "suggested_approach": ""}


# 不同风格的写作指令（语言风格与排版差异由渲染模板负责）
_STYLE_WRITING = {
    "vivid": "语言活泼生动，善用比喻和感叹句，每页要点可带 emoji 图标开头，面向学生讲义的轻松感",
    "minimal": "语言极简，每句话不超过 15 字，要点精炼干练，大量留白感",
    "professional": "语言正式严谨，教学术语规范，要点层次分明（概念/方法/示例）",
}


def _ppt_outline_node(state: PptState) -> dict:
    text = state["text"]
    writing = _STYLE_WRITING.get(state["style"], _STYLE_WRITING["professional"])
    result: PptOutlineOutput = get_structured_model(
        PptOutlineOutput, temperature=0.5, max_tokens=4000
    ).invoke(
        f"你是PPT设计专家。根据以下文档内容生成 {state['slide_count']} 页教学PPT的大纲。"
        f"写作风格要求：{writing}。每页包含标题和3-5个要点（bullets）。\n\n文档内容：\n"
        + text[:8000]
    )
    return {"slides": [s.model_dump() for s in result.slides]}


def build_ppt_outline_graph():
    graph = StateGraph(PptState)
    graph.add_node("generate_outline", _ppt_outline_node)
    graph.add_edge(START, "generate_outline")
    graph.add_edge("generate_outline", END)
    return graph.compile()


_ppt_outline_graph = None


def run_ppt_outline(text: str, style: str = "professional", slide_count: int = 8) -> list[dict]:
    """执行 PPT 大纲生成图，返回 [{title, bullets}]"""
    global _ppt_outline_graph
    if _ppt_outline_graph is None:
        _ppt_outline_graph = build_ppt_outline_graph()
    result = _ppt_outline_graph.invoke(
        {
            "text": text,
            "style": style,
            "slide_count": slide_count,
            "slides": [],
        }
    )
    return result.get("slides", [])
