import asyncio
import threading
from typing import Any

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models import User, UserCreate, UserUpdate


def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"

# ---- 密码哈希并发限流（Argon2 内存带宽争抢是登录吞吐的瓶颈）----
# Argon2id 是 memory-hard 算法：单次校验需连续占用数十 MiB 工作内存，
# 高并发下大量哈希并行执行会打满内存带宽，单次耗时从 ~36ms 劣化到秒级
# （实测并发 50 登录 P50 1.36s、TPS 仅 7.9）。
# 这里用**进程内信号量**把「同时执行的哈希数」限制在接近核数的量级：
# 单个哈希保持快速稳定，其余请求排队等待——典型的**限流换吞吐**。
# 配合路由层 async + asyncio.to_thread，排队期间不占用事件循环线程。
_hash_semaphore = threading.Semaphore(max(1, settings.AUTH_HASH_CONCURRENCY))


def _verify_password_limited(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    """带并发上限的密码校验：在线程池中调用，受信号量保护。"""
    with _hash_semaphore:
        return verify_password(plain_password, hashed_password)


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user


async def authenticate_async(
    *, session: Session, email: str, password: str
) -> User | None:
    """`authenticate` 的异步版本：仅把耗时的哈希校验卸载到线程池并限并发。

    - 按 email 查用户是走索引的毫秒级查询，留在事件循环中执行；
    - 真正昂贵的 Argon2 校验通过 `asyncio.to_thread` 卸载到线程池，
      并由 `_hash_semaphore` 限流，避免高并发下哈希互相争抢内存带宽；
    - 等待信号量的时间是在线程中消耗的，不阻塞事件循环，
      因此大量并发登录请求可以低成本地挂起，服务仍能响应其他接口。

    同步版 `authenticate` 保留给测试与非 HTTP 场景使用。
    """
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # 与同步版一致：用户不存在也要跑一次哈希，防止时序侧信道探测账号是否存在
        await asyncio.to_thread(_verify_password_limited, password, DUMMY_HASH)
        return None
    verified, updated_password_hash = await asyncio.to_thread(
        _verify_password_limited, password, db_user.hashed_password
    )
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user
