"""PRD §5.3 埋点通道：进程内事件总线。

设计取舍：
- 本期为毕设演示规模，埋点以「进程内环形缓冲」实现（默认保留最近 500 条），
  既能被自动化测试直接断言，也能在本地排查时肉眼查看，不引入外部数仓依赖。
- 后续接入真实埋点服务（日志 / 数仓 / 消息队列）时，只需替换 `emit` 的下游实现，
  调用方（路由层）无需改动。

已上报事件：
- assignment_published：作业发布（含 question_count / knowledge_point_count）
- grading_confirmed  ：教师终评确认（含 ai_confidence / adopted）
- mistake_feedback_decided：误区回流被采纳 / 驳回
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

MAX_EVENTS = 500

_LOCK = Lock()
_EVENTS: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)


def emit(event: str, **props: Any) -> dict[str, Any]:
    """上报一条事件，返回落库事件记录（含事件名与时间戳）。"""
    record: dict[str, Any] = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    record.update(props)
    with _LOCK:
        _EVENTS.append(record)
    return record


def recent(limit: int | None = None) -> list[dict[str, Any]]:
    """按时间正序返回事件列表；limit 为 None 时返回全部缓冲。"""
    with _LOCK:
        items = list(_EVENTS)
    if limit is None:
        return items
    return items[-abs(int(limit)) :]


def count(event: str | None = None) -> int:
    """统计事件条数；传入事件名则只统计该事件。"""
    with _LOCK:
        items = list(_EVENTS)
    if event is None:
        return len(items)
    return sum(1 for e in items if e.get("event") == event)


def clear() -> None:
    """清空缓冲（仅供测试隔离使用）。"""
    with _LOCK:
        _EVENTS.clear()
