"""LangChain 兼容的 LLM 客户端 —— 千问优先，DeepSeek / Kimi 备用。

三者均提供 OpenAI 兼容的 /chat/completions 接口，
统一通过 langchain-openai 的 ChatOpenAI 接入 LangGraph，
从而获得流式输出、工具调用与结构化输出能力。

启动时对配置的 provider 逐一探测（1-token 试调用），
自动跳过不可用的（如 Key 失效的千问），缓存可用项。
"""
from functools import lru_cache
from typing import Any

import httpx
from langchain_openai import ChatOpenAI

from app.core.config import settings


def _provider_candidates() -> list[dict]:
    """按优先级返回已配置的 LLM provider"""
    candidates = []
    if settings.QWEN_API_KEY and settings.QWEN_API_KEY != "your-qwen-api-key":
        candidates.append(
            {
                "api_key": settings.QWEN_API_KEY,
                "base_url": settings.QWEN_BASE_URL,
                "model": settings.QWEN_MODEL,
                "name": "qwen",
            }
        )
    if settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY != "your-deepseek-api-key":
        candidates.append(
            {
                "api_key": settings.DEEPSEEK_API_KEY,
                "base_url": settings.DEEPSEEK_BASE_URL,
                "model": settings.DEEPSEEK_MODEL,
                "name": "deepseek",
            }
        )
    if settings.KIMI_API_KEY and settings.KIMI_API_KEY != "your-kimi-api-key":
        candidates.append(
            {
                "api_key": settings.KIMI_API_KEY,
                "base_url": settings.KIMI_BASE_URL,
                "model": settings.KIMI_MODEL,
                "name": "kimi",
            }
        )
    return candidates


def _probe(cfg: dict) -> bool:
    """1-token 试调用，验证 provider 可用"""
    try:
        resp = httpx.post(
            cfg["base_url"].rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg["model"],
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=20.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


@lru_cache(maxsize=1)
def _get_working_config() -> dict:
    """探测并缓存可用的 LLM 配置（千问 → DeepSeek → Kimi，失败自动降级）"""
    candidates = _provider_candidates()
    if not candidates:
        raise RuntimeError(
            "未配置任何 LLM API Key，请在 .env 中设置 QWEN_API_KEY 或 DEEPSEEK_API_KEY"
        )
    for cfg in candidates:
        if _probe(cfg):
            return cfg
    raise RuntimeError("所有已配置的 LLM API Key 均不可用，请检查 .env 中的 Key")


def get_chat_model(
    temperature: float = 0.4,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> ChatOpenAI:
    """获取 LangChain ChatModel（按参数缓存）"""
    cfg = _get_working_config()
    return ChatOpenAI(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=2,
    )


def get_structured_model(
    schema: type,
    temperature: float = 0.2,
    max_tokens: int = 4000,
) -> Any:
    """结构化输出模型（function_calling 模式）。

    为什么不用默认 json_schema 模式：DeepSeek 返回 400
    "This response_format type is unavailable now"（Qwen/Kimi 也不全支持）；
    json_object 模式要求 prompt 必须含 "json" 字样，且解析更脆弱。
    function_calling（工具调用）是三个 provider 都支持的路径。
    """
    return get_chat_model(
        temperature=temperature, max_tokens=max_tokens
    ).with_structured_output(schema, method="function_calling")
