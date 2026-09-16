"""课程表 + 学习任务 API"""
import uuid
from datetime import date
from typing import Any
from fastapi import APIRouter, HTTPException
from sqlmodel import col, func, select, or_
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.models import Schedule, ScheduleCreate, SchedulePublic, SchedulesPublic
from app.models import Task, TaskCreate, TaskPublic, TasksPublic

router = APIRouter(prefix="/reminders", tags=["reminders"])

DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# ==================== 课程表 ====================

@router.get("/schedules", response_model=SchedulesPublic)
def list_schedules(session: SessionDep, current_user: CurrentUser):
    st = select(Schedule).where(Schedule.owner_id == current_user.id).order_by(Schedule.day_of_week, Schedule.start_time)
    items = session.exec(st).all()
    return SchedulesPublic(data=[SchedulePublic.model_validate(s) for s in items], count=len(items))

@router.post("/schedules", response_model=SchedulePublic)
def create_schedule(*, session: SessionDep, current_user: CurrentUser, body: ScheduleCreate):
    s = Schedule.model_validate(body, update={"owner_id": current_user.id})
    session.add(s); session.commit(); session.refresh(s)
    return s

@router.delete("/schedules/{sid}")
def delete_schedule(sid: str, session: SessionDep, current_user: CurrentUser):
    try: uid = uuid.UUID(sid)
    except ValueError: raise HTTPException(400, "无效ID")
    s = session.get(Schedule, uid)
    if not s or s.owner_id != current_user.id: raise HTTPException(404, "不存在")
    session.delete(s); session.commit()
    return {"message": "deleted"}

# ==================== 学习任务 ====================

@router.get("/tasks", response_model=TasksPublic)
def list_tasks(session: SessionDep, current_user: CurrentUser, show_completed: bool = False):
    st = select(Task).where(Task.owner_id == current_user.id)
    if not show_completed:
        st = st.where(Task.completed == False)
    st = st.order_by(Task.due_date.asc(), Task.created_at.desc())
    items = session.exec(st).all()
    return TasksPublic(data=[TaskPublic.model_validate(t) for t in items], count=len(items))

@router.post("/tasks", response_model=TaskPublic)
def create_task(*, session: SessionDep, current_user: CurrentUser, body: TaskCreate):
    t = Task.model_validate(body, update={"owner_id": current_user.id})
    session.add(t); session.commit(); session.refresh(t)
    return t

@router.put("/tasks/{tid}/toggle", response_model=TaskPublic)
def toggle_task(tid: str, session: SessionDep, current_user: CurrentUser):
    try: uid = uuid.UUID(tid)
    except ValueError: raise HTTPException(400, "无效ID")
    t = session.get(Task, uid)
    if not t or t.owner_id != current_user.id: raise HTTPException(404, "不存在")
    t.completed = not t.completed
    session.add(t); session.commit(); session.refresh(t)
    return t

@router.delete("/tasks/{tid}")
def delete_task(tid: str, session: SessionDep, current_user: CurrentUser):
    try: uid = uuid.UUID(tid)
    except ValueError: raise HTTPException(400, "无效ID")
    t = session.get(Task, uid)
    if not t or t.owner_id != current_user.id: raise HTTPException(404, "不存在")
    session.delete(t); session.commit()
    return {"message": "deleted"}

# ==================== 今日概览 ====================

class TodayOverview(BaseModel):
    today_schedule: list[SchedulePublic]
    upcoming_tasks: list[TaskPublic]
    day_name: str

@router.get("/today", response_model=TodayOverview)
def today_overview(session: SessionDep, current_user: CurrentUser):
    today = date.today()
    dow = today.weekday()  # 0=Mon
    schedules = session.exec(
        select(Schedule).where(Schedule.owner_id == current_user.id, Schedule.day_of_week == dow).order_by(Schedule.start_time)
    ).all()
    today_str = today.isoformat()
    tasks = session.exec(
        select(Task).where(Task.owner_id == current_user.id, Task.completed == False, or_(Task.due_date == today_str, Task.due_date == "")).order_by(Task.created_at.desc()).limit(10)
    ).all()
    return TodayOverview(
        today_schedule=[SchedulePublic.model_validate(s) for s in schedules],
        upcoming_tasks=[TaskPublic.model_validate(t) for t in tasks],
        day_name=DAY_NAMES[dow],
    )
