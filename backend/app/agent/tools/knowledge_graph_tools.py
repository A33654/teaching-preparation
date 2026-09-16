"""Neo4j 知识图谱查询工具（独立封装）。

调用时机完全由大模型自主判断：模型结合工具描述、系统提示中的
「工具调用时机指南」与当前会话状态，决定是否调用、何时调用、调用哪个工具。

本模块同时提供可确定性复用的工具函数，供强制触发兜底节点直接调用
（见 app/agent/tools/registry.py 的 detect_kg_intent / refine_query）。
"""
import json
from typing import Callable

from langchain_core.tools import tool

from app.knowledge_graph import KnowledgeGraphRepository


def _sources_payload(result: list[dict]) -> dict:
    """统一工具返回结构：{result, sources}"""
    return {
        "result": result,
        "sources": [
            {
                "type": "knowledge_point",
                "name": item.get("name", ""),
                "id": item.get("id", ""),
            }
            for item in result
        ],
    }


def _db_error(e: Exception) -> str:
    """数据库异常 → 结构化错误 JSON（模型可读，不中断 ReAct 循环）。

    注意：不返回 Python traceback，避免把内部细节泄给模型；
    模型看到 error 字段后应如实告知用户「图谱暂时不可用」，不得编造结果。
    """
    return json.dumps(
        {"result": [], "sources": [], "error": "知识图谱数据库异常，请稍后重试"},
        ensure_ascii=False,
    )


def build_knowledge_graph_tools(
    owner_id: str,
    repo: KnowledgeGraphRepository,
) -> list[Callable]:
    """构建知识图谱查询工具集（按用户绑定权限）"""

    @tool
    def search_knowledge_graph(query: str, top_k: int = 10) -> str:
        """在用户的知识图谱中检索知识点。

        【调用时机】当问题涉及知识点定义、考点、知识脉络、前置/包含/关联关系时调用；
        纯寒暄、常识问答、与教学无关的问题不要调用。
        【输入】query 为知识点名称或核心概念词（如「勾股定理」「二次函数」），
        提取问题的核心词而非整句；top_k 为返回条数。
        【输出】匹配的知识点节点列表（含描述与考点标记）。
        """
        try:
            results = repo.search_knowledge_points(query, owner_id=owner_id, top_k=top_k)
        except Exception as e:
            return _db_error(e)
        brief = [
            {
                "id": r["id"],
                "name": r["name"],
                "subject": r["subject"],
                "description": (r["description"] or "")[:200],
                "is_key_point": r["is_key_point"],
            }
            for r in results
        ]
        return json.dumps(
            {"result": brief, "sources": _sources_payload(results)["sources"]},
            ensure_ascii=False,
        )

    @tool
    def get_knowledge_point_detail(kp_id: str) -> str:
        """获取单个知识点的详细信息及其直接关系。

        【调用时机】search_knowledge_graph 命中后，需要某个知识点的完整描述、
        前置知识或直接关联关系时调用。
        【输入】知识点 ID（来自 search_knowledge_graph 的返回结果）。
        """
        try:
            kp = repo.get_knowledge_point(kp_id)
            if not kp:
                return json.dumps(
                    {"result": [], "sources": [], "error": "知识点不存在"}, ensure_ascii=False
                )
            relations = repo.get_relations(kp_id)
        except Exception as e:
            return _db_error(e)
        return json.dumps(
            {"result": [{**kp, "relations": relations}], "sources": [kp]},
            ensure_ascii=False,
        )

    @tool
    def get_knowledge_neighbors(kp_id: str, depth: int = 1) -> str:
        """沿图谱关系遍历某知识点的邻居（前置/包含/相关）。

        【调用时机】需要梳理知识脉络、扩展相关知识点时调用，
        通常在 get_knowledge_point_detail 之后按需使用。
        【输入】知识点 ID 与遍历深度（1-2）。
        """
        try:
            neighbors = repo.get_neighbors(kp_id, depth=min(max(depth, 1), 2))
        except Exception as e:
            return _db_error(e)
        brief = [
            {"id": n["id"], "name": n["name"], "subject": n["subject"]}
            for n in neighbors
        ]
        return json.dumps(
            {"result": brief, "sources": _sources_payload(neighbors[:5])["sources"]},
            ensure_ascii=False,
        )

    return [search_knowledge_graph, get_knowledge_point_detail, get_knowledge_neighbors]
