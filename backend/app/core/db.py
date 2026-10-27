from sqlmodel import Session, SQLModel, create_engine, select

from app import crud
from app.core.config import settings
from app.models import User, UserCreate

engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    # 自动探测并踢掉失效连接（数据库容器重启/网络抖动后连接池里的旧连接会挂起请求）
    pool_pre_ping=True,
    # 连接池按并发量配置（默认值 5/10 在 --workers 多进程 + 高并发下会 QueuePool 超时）
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # 确保所有模型（含作业/提交相关表）已注册到 metadata
    from app import models  # noqa: F401

    # 与 Alembic 互补：对新增表/列做兜底建表，保证开发/测试/本地直接启动也能工作。
    # 生产环境仍由 Alembic 迁移统一管理表结构；此处 create_all 幂等，不会改动已存在表。
    SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)
