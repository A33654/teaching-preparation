"""LangGraph 各图的状态定义"""
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from typing_extensions import NotRequired


class ChatState(TypedDict):
    """教学助手问答图状态"""
    # 对话消息（add_messages 自动合并为列表）
    messages: Annotated[list[BaseMessage], add_messages]
    # langgraph 1.x prebuilt ReAct 的剩余步数（ManagedValue，由运行时按
    # recursion_limit 自动注入——勿在初始 state 中手动赋值，否则
    # 工具调用场景会被误判为「步数耗尽」而返回占位回答）
    remaining_steps: NotRequired[RemainingSteps]
    # 当前用户 ID（工具权限隔离）
    owner_id: str
    # 用户画像（学科/学段，用于个性化回答）
    user_profile: dict[str, Any]
    # 检索引用来源（由工具结果汇总）
    sources: list[dict]
    # 强制触发兜底：规则层识别出的图谱意图候选（原消息文本），无则 None
    force_candidate: str | None


class ExtractionState(TypedDict):
    """文档知识抽取图状态"""
    text: str
    owner_id: str
    document_id: str
    # 输出
    subject: str
    summary: str
    knowledge_points: list[dict]
    relations: list[dict]
    kp_ids: list[str]
    error: str


class LessonPlanState(TypedDict):
    """教案生成图状态（固定编排流水线：查询→RAG检索→生成→校验）"""
    owner_id: str
    knowledge_point_ids: list[str]
    subject: str
    grade_level: str
    requirements: str
    style: str
    chapter: str
    # 中间产物
    graph_context: list[dict]
    materials: list[dict]  # RAG 教材检索素材
    # 输出
    lesson_plan: dict[str, Any]
    verification_report: dict[str, Any]
    error: str


class SummarizeState(TypedDict):
    """文档概括图状态"""
    text: str
    # 输出
    summary: str
    key_topics: list[str]
    suggested_approach: str
    slides: list[dict]


class PptState(TypedDict):
    """PPT 大纲生成图状态"""
    text: str
    style: str
    slide_count: int
    slides: list[dict]


# 关系类型字面量
RelationTypeLiteral = Literal["prerequisite", "contains", "related_to"]
