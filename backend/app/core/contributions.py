"""共建贡献事件：统一写入与周期计算（防重复计数）。"""
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import (
    ContributionEvent,
    ContributionType,
    ResourceType,
    User,
)


def current_period(now: datetime | None = None) -> str:
    """当前周期标识，形如 2026-W43（按 ISO 周）。"""
    now = now or datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def emit_contribution(
    session: Session,
    *,
    user: User,
    event_type: ContributionType,
    resource_type: ResourceType | None = None,
    resource_id=None,
    points: int = 1,
    dedupe_key: str | None = None,
) -> ContributionEvent | None:
    """写入一条贡献事件；若给定 dedupe_key 且已存在则跳过（防重复计数）。"""
    if user.org_id is None:
        # 无组织用户不计入共建贡献
        return None
    if dedupe_key:
        existing = session.exec(
            select(ContributionEvent.id).where(
                ContributionEvent.dedupe_key == dedupe_key,
                ContributionEvent.user_id == user.id,
            )
        ).first()
        if existing:
            return None
    event = ContributionEvent(
        user_id=user.id,
        org_id=user.org_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        points=points,
        period=current_period(),
        dedupe_key=dedupe_key,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
