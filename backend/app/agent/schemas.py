"""LLM 结构化输出的 Pydantic Schema（LangChain with_structured_output 用）"""
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgePointExtract(BaseModel):
    """单个知识点抽取结果"""
    name: str = Field(description="知识点名称，简洁精准，如「勾股定理」")
    description: str = Field(description="一句话描述该知识点的核心内容")
    subject: str = Field(description="所属学科")
    difficulty: int = Field(default=1, ge=1, le=5, description="难度 1-5")
    is_key_point: bool = Field(default=False, description="是否核心考点")


class RelationExtract(BaseModel):
    """知识点关系抽取结果"""
    source_name: str = Field(description="源知识点名称（必须与抽取的知识点名称完全一致）")
    target_name: str = Field(description="目标知识点名称（必须与抽取的知识点名称完全一致）")
    relation_type: Literal["prerequisite", "contains", "related_to"] = Field(
        description="关系类型: prerequisite=前置知识, contains=包含, related_to=相关"
    )


class ExtractionOutput(BaseModel):
    """文档知识抽取整体输出"""
    subject: str = Field(description="文档所属学科")
    knowledge_points: list[KnowledgePointExtract] = Field(
        description="提取的知识点列表（去重，5-30 个为宜）"
    )
    relations: list[RelationExtract] = Field(
        description="知识点之间的关系列表（仅引用已提取的知识点名称）"
    )


class LessonPlanOutput(BaseModel):
    """教案生成输出"""
    title: str = Field(description="教案标题")
    subject: str = Field(description="学科")
    grade_level: str = Field(description="学段：小学/初中/高中")
    teaching_objectives: str = Field(description="教学目标，分条列出")
    teaching_process: str = Field(description="详细教学过程，含环节与时间分配")
    key_points: list[str] = Field(default_factory=list, description="教学重点")
    difficult_points: list[str] = Field(default_factory=list, description="教学难点")


class SummarizeOutput(BaseModel):
    """文档概括输出"""
    summary: str = Field(description="文档内容概括（200-400字）")
    key_topics: list[str] = Field(description="核心主题列表（3-8个）")
    suggested_approach: str = Field(description="教学建议")


class SlideContent(BaseModel):
    """单页 PPT 内容"""
    title: str = Field(description="页面标题")
    bullets: list[str] = Field(description="3-5 个要点")


class PptOutlineOutput(BaseModel):
    """PPT 大纲输出"""
    slides: list[SlideContent] = Field(description="幻灯片内容列表")
