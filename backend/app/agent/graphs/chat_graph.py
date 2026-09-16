"""教学助手问答图 —— 混合决策架构（灵活性与稳定性兼顾）。

图结构:
    START → check_force_kg（规则层意图识别）
             ├─ 命中图谱意图 → forced_kg_query（确定性强制预检索，校验后注入结果）
             └─ 未命中       → agent
    forced_kg_query → agent（LangGraph ReAct 子图：LLM 自主决策调用工具）
    agent → END

设计原则:
- 灵活性: 工具调用时机由大模型结合工具描述、系统提示与会话状态自主判断，
  预检索结果注入后，模型仍可自主追加 detail/neighbors/文档检索;
- 稳定性: 规则层识别图谱意图后强制预检索一次，保证回答基于真实图谱数据，
  防止模型跳过工具直接空答（可通过 AGENT_FORCE_KG_TRIGGER 配置开关）。
"""
import json
from typing import Any, AsyncGenerator

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from sqlmodel import Session

from app.agent.llm import get_chat_model
from app.agent.state import ChatState
from app.agent.tools import build_agent_tools, build_forced_search_tool, detect_kg_intent, refine_query
from app.core.config import settings
from app.knowledge_graph import KnowledgeGraphRepository

# 强制预检索结果的消息前缀标记（流式事件解析用，请勿与用户消息混淆）
FORCED_KG_PREFIX = "【系统预检索结果】"

SYSTEM_PROMPT = """你是「AI 教学助手」，一名资深的教育专家。你的定位是**教案迭代润色助手**：
完整教案由「智能备课工作台」的固定流水线生成，你负责教师生成教案后的二次修改交互
（如「把习题增加 2 道」「简化板书」「把这个知识点讲浅一点」），也负责日常备课答疑。

## 工具调用时机指南（由你自主判断）

- 问题涉及**知识点定义、考点、知识脉络、前置/包含/关联关系** → 调用知识图谱工具（search_knowledge_graph 起步，命中后用 get_knowledge_point_detail / get_knowledge_neighbors 展开）
- 问题涉及**教材原文、讲义内容、已上传文档的具体表述** → 调用文档检索工具 search_documents
- **寒暄、常识问答、与教学无关** → 直接回答，不调用任何工具
- 同一种检索不要重复调用；图谱无结果时明确说明「知识图谱中未收录此内容」，绝不编造

## 关于「系统预检索结果」

对话中可能出现以「【系统预检索结果】」开头的消息（系统强制预检索兜底产生）。
这是规则层为保证回答基于真实图谱数据而预先检索的结果：
- 优先基于该结果回答，无需重复调用 search_knowledge_graph；
- 需要更多细节（完整描述/关联关系）时，再按需调用 get_knowledge_point_detail / get_knowledge_neighbors。

## 回答规则

- 润色教案时：保留原教案结构，只做针对性修改，先说明改了什么
- 体现知识点的前置依赖与关联脉络，可用编号/要点组织
- 语言简洁专业，面向教师备课场景
- 教师学段：{grade_level}；学科：{subject}
"""


def _last_user_message(state: ChatState) -> str:
    """取最后一条用户消息"""
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage) and isinstance(m.content, str):
            return m.content
    return ""


def build_chat_graph(
    *,
    owner_id: str,
    user_profile: dict[str, Any],
    session: Session,
    repo: KnowledgeGraphRepository,
) -> Any:
    """构建绑定当前用户会话的混合决策问答图。

    agent/tools 节点平铺在本图（不能用子图）：子图的 custom 流不会
    传播到外层 astream，token 级流式会失效（langgraph 1.2 行为）。
    """
    tools = build_agent_tools(owner_id=owner_id, session=session, repo=repo)
    model = get_chat_model(temperature=0.4, max_tokens=2000)
    prompt = SYSTEM_PROMPT.format(
        grade_level=user_profile.get("grade_level") or "未设置",
        subject=user_profile.get("subject") or "未设置",
    )
    model_with_tools = model.bind_tools(tools)

    def agent_node(state: ChatState, config: RunnableConfig) -> dict:
        """agent 节点：显式 model.stream（传 config）。

        节点在顶层图（非子图）时，流式 chunk 会被 langgraph 自动写入
        stream_mode="messages" 流（on_llm_new_token 捕获），SSE 直接
        消费 AIMessageChunk 即可，无需手动 writer。
        config 参数必须注解为 RunnableConfig，langgraph 才会注入。
        """
        messages: list[BaseMessage] = list(state["messages"])
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=prompt), *messages]
        chunks: list[AIMessageChunk] = []
        for chunk in model_with_tools.stream(messages, config):
            chunks.append(chunk)
        if not chunks:
            return {"messages": [AIMessage(content="")]}
        merged: AIMessageChunk = chunks[0]
        for c in chunks[1:]:
            merged = merged + c
        return {"messages": [merged]}

    # ==================== 节点 1: 规则层意图识别 ====================

    def check_force_kg(state: ChatState) -> dict:
        """规则层识别图谱查询意图（不调用 LLM、不访问 Neo4j）"""
        if not settings.AGENT_FORCE_KG_TRIGGER:
            return {"force_candidate": None}
        return {"force_candidate": detect_kg_intent(_last_user_message(state))}

    def route_after_check(state: ChatState) -> str:
        return "force" if state.get("force_candidate") else "pass"

    # ==================== 节点 2: 强制预检索兜底 ====================

    def forced_kg_query(state: ChatState) -> dict:
        """确定性预检索：校验后复用与 Agent 完全相同的图谱工具，结果注入会话。

        注意：注入为 HumanMessage 而非 ToolMessage——OpenAI 兼容接口要求
        每个 tool 消息前必须有对应的 assistant tool_call，强制注入的
        ToolMessage 没有前置 tool_call，会导致 LLM 接口 400。
        """
        message = state.get("force_candidate") or ""
        if not message:
            return {"force_candidate": None}

        # 校验规则 1: 用户图谱为空时不强制（无谓调用，交给模型自行判断）
        if repo.count_knowledge_points(owner_id) == 0:
            return {"force_candidate": None}

        # 校验规则 2: 提取查询词（已有知识点名优先）
        query = refine_query(message, repo.list_knowledge_point_names(owner_id))
        if not query:
            return {"force_candidate": None}

        # 复用与 Agent 相同的工具函数，保证行为一致
        search_tool = build_forced_search_tool(owner_id, repo)
        result_str = search_tool.invoke({"query": query, "top_k": settings.AGENT_CHAT_TOP_K})

        forced_message = HumanMessage(
            content=f"{FORCED_KG_PREFIX}检索词「{query}」的图谱结果：\n{result_str}"
        )
        return {"messages": [forced_message], "force_candidate": None}

    # ==================== 组装图 ====================

    graph = StateGraph(ChatState)
    graph.add_node("check_force_kg", check_force_kg)
    graph.add_node("forced_kg_query", forced_kg_query)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "check_force_kg")
    graph.add_conditional_edges(
        "check_force_kg",
        route_after_check,
        {"force": "forced_kg_query", "pass": "agent"},
    )
    graph.add_edge("forced_kg_query", "agent")
    # ReAct 工具循环：agent ⇄ tools（tools_condition 读最后一条消息的 tool_calls）
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def _messages_from_history(history: list[dict]) -> list[BaseMessage]:
    """把前端传来的历史消息转为 LangChain 消息"""
    messages: list[BaseMessage] = []
    for item in history[-12:]:  # 最多保留 12 条历史
        role = item.get("role")
        text = item.get("content") or ""
        if role == "user" and text:
            messages.append(HumanMessage(content=text))
        elif role == "assistant" and text:
            messages.append(AIMessageChunk(content=text))
    return messages


def _extract_sources(tool_message: ToolMessage) -> list[dict]:
    """从工具返回的 JSON 中提取引用来源"""
    content = tool_message.content
    if not isinstance(content, str):
        return []
    return _extract_sources_from_text(content)


def _extract_sources_from_text(content: str) -> list[dict]:
    """从含 JSON 的文本（如强制预检索注入消息）中提取引用来源"""
    try:
        data = json.loads(content)
        return data.get("sources", []) or []
    except (json.JSONDecodeError, TypeError):
        # 注入消息格式：【系统预检索结果】检索词「...」的图谱结果：\n{json}
        json_start = content.find("{")
        if json_start < 0:
            return []
        try:
            data = json.loads(content[json_start:])
            return data.get("sources", []) or []
        except (json.JSONDecodeError, TypeError):
            return []


async def astream_chat_events(
    graph: Any,
    *,
    owner_id: str,
    user_profile: dict[str, Any],
    history: list[dict],
    message: str,
) -> AsyncGenerator[dict, None]:
    """以 SSE 事件流方式执行问答图。

    事件类型:
    - token:       大模型逐字输出
    - tool_result: 工具调用完成（含强制预检索兜底，同样以 tool_result 呈现）
    - done:        完成，携带完整回复与汇总来源
    - error:       出错
    """
    messages = _messages_from_history(history)
    messages.append(HumanMessage(content=message))
    state: ChatState = {
        "messages": messages,
        # remaining_steps 由运行时注入，勿手动赋值（见 state.py 说明）
        "owner_id": owner_id,
        "user_profile": user_profile,
        "sources": [],
        "force_candidate": None,
    }

    sources: list[dict] = []
    seen_source_ids: set[str] = set()
    reply_parts: list[str] = []
    # 双流合一：
    # - messages: LLM 流式 token（AIMessageChunk）+ 工具调用结果（ToolMessage）
    # - values:  最终 state —— 回复兜底（模型非流式时仍能提取完整回复）
    last_state: dict | None = None
    try:
        async for mode, chunk in graph.astream(
            state,
            stream_mode=["messages", "values"],
            config={"recursion_limit": settings.AGENT_MAX_ITERATIONS + 8},
        ):
            if mode == "values":
                last_state = chunk
                continue
            msg_chunk, metadata = chunk
            # 强制预检索兜底注入的消息（HumanMessage 前缀标记）
            if (
                isinstance(msg_chunk, HumanMessage)
                and isinstance(msg_chunk.content, str)
                and msg_chunk.content.startswith(FORCED_KG_PREFIX)
            ):
                forced_sources = _extract_sources_from_text(msg_chunk.content)
                for s in forced_sources:
                    key = f"{s.get('type')}:{s.get('id') or s.get('name')}"
                    if key not in seen_source_ids:
                        seen_source_ids.add(key)
                        sources.append(s)
                yield {
                    "type": "tool_result",
                    "tool_name": "search_knowledge_graph",
                    "sources": forced_sources,
                    "forced": True,
                }
            elif isinstance(msg_chunk, ToolMessage):
                for s in _extract_sources(msg_chunk):
                    key = f"{s.get('type')}:{s.get('id') or s.get('name')}"
                    if key not in seen_source_ids:
                        seen_source_ids.add(key)
                        sources.append(s)
                yield {
                    "type": "tool_result",
                    "tool_name": msg_chunk.name,
                    "sources": _extract_sources(msg_chunk),
                    "forced": False,
                }
            elif isinstance(msg_chunk, AIMessageChunk):
                content = msg_chunk.content
                if isinstance(content, str) and content:
                    reply_parts.append(content)
                    yield {"type": "token", "content": content}
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part.get("text", "")
                            reply_parts.append(text)
                            yield {"type": "token", "content": text}
    except Exception as e:
        yield {"type": "error", "content": str(e)}
        return

    # 最终回复：优先流式 token；缺失时从最终 state 的最后一条 AIMessage 提取
    reply = "".join(reply_parts)
    if not reply and last_state:
        messages = last_state.get("messages") or []
        last_msg = messages[-1] if messages else None
        if isinstance(last_msg, AIMessage):
            content = last_msg.content
            if isinstance(content, str):
                reply = content
            elif isinstance(content, list):
                reply = "".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )

    yield {"type": "done", "reply": reply, "sources": sources}
