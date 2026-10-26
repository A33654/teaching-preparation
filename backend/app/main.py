import logging
import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
def on_startup() -> None:
    """应用启动时初始化 Neo4j 约束与索引，并按配置预置示范知识库"""
    from app.core.neo4j import get_neo4j_driver, init_neo4j_constraints

    try:
        init_neo4j_constraints(get_neo4j_driver())
    except Exception:
        pass  # Neo4j 未就绪时跳过，首次使用时按需重试

    # 演示库自动灌库：图谱为空时预置示范知识库（幂等，已灌则跳过）
    if settings.SEED_DEMO_ON_STARTUP:
        try:
            from app.initial_data import seed_knowledge_graph

            seed_knowledge_graph()
        except Exception as e:  # 数据库/Neo4j 未就绪时不影响应用启动
            logger.warning("演示库自动灌库跳过：%s", e)
