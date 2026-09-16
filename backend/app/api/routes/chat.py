"""AI 教学助手问答 API —— LangGraph ReAct Agent，SSE 流式输出。

事件流（SSE data 为 JSON）:
- {"type": "token", "content": "..."}            逐字输出
- {"type": "tool_result", "tool_name": "...", "sources": [...]}  工具调用完成
- {"type": "done", "reply": "...", "sources": [...]}             结束
- {"type": "error", "content": "..."}                             出错
"""
import json
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.graphs import astream_chat_events, build_chat_graph
from app.api.deps import CurrentUser, SessionDep
from app.knowledge_graph import KnowledgeGraphRepository

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{"role": "user|assistant", "content": "..."}]
    mode: str = "sse"  # sse=流式 | json=一次性返回


class ChatResponse(BaseModel):
    """非流式响应（mode=json 时使用）"""
    reply: str
    sources: list[dict]


def _build_graph(session, current_user):
    """按请求构建绑定用户上下文的问答图"""
    repo = KnowledgeGraphRepository()
    return build_chat_graph(
        owner_id=str(current_user.id),
        user_profile={
            "subject": current_user.subject,
            "grade_level": current_user.grade_level,
            "full_name": current_user.full_name,
        },
        session=session,
        repo=repo,
    )


async def _sse_generator(graph, body: ChatRequest, current_user) -> AsyncGenerator[str, None]:
    """SSE 事件生成器"""
    async for event in astream_chat_events(
        graph,
        owner_id=str(current_user.id),
        user_profile={
            "subject": current_user.subject,
            "grade_level": current_user.grade_level,
        },
        history=body.history,
        message=body.message,
    ):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/")
async def chat(
    body: ChatRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    """RAG 问答：LangGraph Agent 自主检索知识图谱与文档后回答。

    mode=sse（默认）: Server-Sent Events 流式返回
    mode=json:        一次性 JSON 返回（非流式场景）
    """
    if not body.message.strip():
        if body.mode == "json":
            return ChatResponse(reply="请输入问题", sources=[])
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'content': '请输入问题'}, ensure_ascii=False)}\n\n"]),
            media_type="text/event-stream",
        )

    graph = _build_graph(session, current_user)

    if body.mode == "sse":
        return StreamingResponse(
            _sse_generator(graph, body, current_user),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 非流式：收集事件后组装
    reply_parts: list[str] = []
    sources: list[dict] = []
    error = ""
    async for event in astream_chat_events(
        graph,
        owner_id=str(current_user.id),
        user_profile={"subject": current_user.subject, "grade_level": current_user.grade_level},
        history=body.history,
        message=body.message,
    ):
        if event["type"] == "token":
            reply_parts.append(event["content"])
        elif event["type"] == "done":
            sources = event.get("sources", [])
        elif event["type"] == "error":
            error = event.get("content", "")
    if error and not reply_parts:
        return ChatResponse(reply=f"回答失败: {error}", sources=[])
    return ChatResponse(reply="".join(reply_parts), sources=sources)
