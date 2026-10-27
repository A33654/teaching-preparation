import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "changethis123"
    NEO4J_DATABASE: str = "neo4j"

    # ---- 密码哈希（Argon2id）成本参数 ----
    # P02：默认 time_cost=3 / memory_cost=65536(64MiB) 下单次哈希约 110ms，
    # 登录并发时因内存带宽争抢放大到 P50 619ms。这里下调为
    # time_cost=2 / memory_cost=32768(32MiB)，单次哈希约 36ms，
    # 仍高于 OWASP 建议下限（m=19MiB, t=2），属于安全与性能的折中。
    # 注意：仅影响「新写入」的密码哈希；已存哈希自带参数，校验照旧可用，无需重置用户密码。
    ARGON2_TIME_COST: int = 2
    ARGON2_MEMORY_COST: int = 32768  # 单位 KiB

    # LangGraph Agent 配置
    AGENT_MAX_ITERATIONS: int = 8  # ReAct agent 最大工具调用轮数
    AGENT_CHAT_TOP_K: int = 10  # 每次检索返回的图节点/文档条数
    # 知识图谱强制触发兜底开关：True 时规则层识别图谱意图后强制预检索一次，
    # 保证回答基于真实图谱数据；False 时完全由大模型自主决定调用时机
    AGENT_FORCE_KG_TRIGGER: bool = True

    # 演示库自动灌库：启动时若 Neo4j 图谱为空，自动预置示范知识库（初中物理 人教版八上），
    # 避免「教师一进来库空 → 全 RAG 兜底」的演示翻车。生产环境可置为 False。
    # 该逻辑幂等，已灌库则直接跳过；编排见 app/initial_data.seed_knowledge_graph。
    SEED_DEMO_ON_STARTUP: bool = True

    # ---- 数据库连接池 ----
    # SQLAlchemy 默认 pool_size=5 / max_overflow=10（面向单进程低并发的默认值）。
    # 本项目以 `--workers N` 多进程部署，且接口在整个请求期间持有 session，
    # 默认值高并发下必然 QueuePool timeout（实测并发 100/300 出现 30s 超时雪崩）。
    # 注意：每个 worker 的连接上限 = pool_size + max_overflow，
    # 全局上限 = 该值 × worker 数，必须小于 PostgreSQL 的 max_connections。
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30

    # ---- 缓存（Redis）----
    # 空字符串 = 关闭缓存（未部署 Redis 时自动降级，不影响可用性）。
    # 开启后用于缓存「知识点列表」等高频只读图谱查询结果，避免每次请求都打 Neo4j。
    REDIS_URL: str = ""
    # 知识点列表缓存 TTL（秒）。图谱写入（新增/修改/删除知识点）时会主动失效。
    REDIS_CACHE_TTL: int = 60

    # ---- 密码哈希并发上限（反内存带宽争抢）----
    # Argon2 是内存硬（memory-hard）算法：单次哈希需连续占用 m=32MiB 工作内存，
    # 高并发下大量哈希同时执行会**打满内存带宽**，单次耗时从 ~36ms 劣化到秒级
    # （实测并发 50 登录 P50 达 1.36s、TPS 仅 7.9）。
    # 用信号量把「同时执行的哈希数」限制在接近 CPU 核数的量级，让每个哈希快而稳定，
    # 其余请求排队等待——总吞吐反而显著提升。这是**限流换吞吐**的典型权衡。
    # 该值是**每个 worker 进程**的并发上限，实际全局并发 = 本值 × worker 数。
    AUTH_HASH_CONCURRENCY: int = 4

    # Qwen (千问) - 主 LLM
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    # DeepSeek - 备用
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Kimi (Moonshot) - 备用（OpenAI 兼容接口，支持工具调用）
    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    KIMI_MODEL: str = "kimi-k2.6"

    # ---- FR-08 误区回流 ----
    # 知识点错误率 ≥ 该阈值时，推送「建议补入图谱误区」卡片（0-1，默认 40%）
    MISCONCEPTION_BACKFLOW_THRESHOLD: float = 0.4
    # ---- FR-07 错误率统计 ----
    # 主观题得分率 < 该阈值即判定为「未掌握 / 计入错误」（默认 60%）
    SUBJECTIVE_WRONG_SCORE_RATIO: float = 0.6
    # ---- FR-05/PRD §7② AI 置信度门槛 ----
    # AI 建议置信度 < 该阈值 → needs_human，且终评必须由教师手填（不得一键采纳）
    AI_CONFIDENCE_HUMAN_THRESHOLD: float = 0.7

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
