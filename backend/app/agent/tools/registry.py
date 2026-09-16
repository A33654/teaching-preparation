"""Agent 工具注册中心。

职责：
1. 装配工具集（知识图谱 + 文档检索），供 ReAct Agent 自主选择调用；
2. 提供知识图谱「强制触发兜底」的确定性规则：
   - detect_kg_intent: 规则层识别图谱查询意图（关键词模式，非 LLM）；
   - refine_query:    从消息中提取查询词（优先匹配已有知识点名）。

设计原则（兼顾灵活性与稳定性）：
- 灵活性：调用时机由大模型结合工具描述、会话状态与系统提示自主判断；
- 稳定性：当规则层判定为图谱意图时，强制预检索一次并把结果注入会话，
  即使大模型未主动调用工具，回答也基于真实图谱数据（可配置开关）。
"""
import re
from typing import Callable

from sqlmodel import Session

from app.agent.tools.document_tools import build_document_tools
from app.agent.tools.knowledge_graph_tools import build_knowledge_graph_tools
from app.knowledge_graph import KnowledgeGraphRepository

# ==================== 强制触发兜底规则（配置化场景） ====================

# 图谱查询意图关键词模式（命中即视为候选意图，进入强制预检索兜底）
KG_INTENT_PATTERNS: list[str] = [
    r"知识点|知识图谱|图谱|考点",
    r"前置|先学|需要先掌握|基础是|依赖",
    r"包含|包括|涵盖|细分|分为",
    r"关联|脉络|梳理|知识结构|知识框架",
]

# 纯寒暄/结束语——不触发兜底（由大模型自行决定是否调用工具）
GREETING_RE = re.compile(
    r"^(你好|您好|hi|hello|嗨|在吗|早上好|下午好|晚上好|谢谢|感谢|再见|拜拜)"
    r"[\s!！。.~～]*$",
    re.IGNORECASE,
)


def detect_kg_intent(message: str) -> str | None:
    """确定性意图识别：命中图谱意图返回原消息，否则 None。

    仅作强制触发兜底候选；最终是否调用工具由大模型自主判断。
    """
    msg = message.strip()
    if len(msg) < 4:
        return None
    if GREETING_RE.fullmatch(msg):
        return None
    if not any(re.search(p, msg) for p in KG_INTENT_PATTERNS):
        return None
    return msg


def refine_query(message: str, known_names: list[str]) -> str | None:
    """从消息中提取查询词（供强制预检索使用）。

    优先级：
    1. 消息中包含已有知识点名称 → 直接使用该名称（最长匹配优先）；
    2. 否则剥离意图动词/名词，截取核心片段。
    """
    # 1. 已有知识点名匹配
    best = None
    for name in known_names:
        if name in message and (best is None or len(name) > len(best)):
            best = name
    if best:
        return best

    # 2. 剥离意图动词与名词（循环剥离，处理「帮我梳理一下...」这类多层前缀）
    q = message
    intent_verbs = (
        "帮我|请|我想|我要|麻烦|梳理一下|介绍一下|查询|查一下|讲解|讲讲|请问"
        "|什么是|有哪些|说说|看看|讲一下"
    )
    intent_nouns = (
        "知识点|知识图谱|图谱|关系|内容|情况|脉络|考点|是什么|有哪些"
        "|是什么关系|的结构|的框架"
    )
    for _ in range(3):
        new_q = re.sub(rf"^({intent_verbs})", "", q)
        new_q = re.sub(rf"({intent_nouns})+$", "", new_q)
        if new_q == q:
            break
        q = new_q
    q = q.strip(" \t\r\n，。！？!?、的")
    return q[:15] or None


# ==================== 工具装配 ====================


def build_agent_tools(
    owner_id: str,
    session: Session,
    repo: KnowledgeGraphRepository,
) -> list[Callable]:
    """装配全部 Agent 工具（知识图谱 + 文档检索）"""
    return [
        *build_knowledge_graph_tools(owner_id=owner_id, repo=repo),
        *build_document_tools(owner_id=owner_id, session=session),
    ]


def build_forced_search_tool(
    owner_id: str,
    repo: KnowledgeGraphRepository,
) -> Callable:
    """获取知识图谱检索工具（供强制触发兜底节点确定性复用）"""
    return build_knowledge_graph_tools(owner_id=owner_id, repo=repo)[0]
