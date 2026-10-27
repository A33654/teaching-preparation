"""轻量 Redis 缓存（可选组件）。

设计原则：

- **Redis 不可用不影响业务**：`REDIS_URL` 为空、或连接/操作失败时自动降级为「不缓存」，
  绝不让缓存故障传导成接口 500。降级后每隔 `REDIS_RETRY_AFTER` 秒做一次探测，
  Redis 恢复后自动重新启用。
- **同步客户端**：本项目路由以同步 `def` 为主（见 docs/architecture.md §2），
  同步客户端在 worker 线程池内直接使用即可，避免为缓存引入大范围 async 改造。
- 写入侧需主动失效：缓存的是「知识点列表」等图谱只读结果，
  任何知识点的新增/修改/删除都必须调用 `delete_prefix` 清理，防止读到陈旧数据。
"""
from __future__ import annotations

import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)

# 降级后重新探测 Redis 的间隔（秒）
REDIS_RETRY_AFTER = 30.0


class _Cache:
    """带熔断的 Redis 缓存客户端（模块级单例 `cache`）。"""

    def __init__(self) -> None:
        self._client = None
        # 上次失败时刻；None 表示当前可用
        self._disabled_at: float | None = None
        self._warned = False

    # ---------------- 可用性判定 ----------------

    def enabled(self) -> bool:
        """当前是否允许访问 Redis（未配置 / 熔断期内均返回 False）。"""
        if not settings.REDIS_URL:
            return False
        if self._disabled_at is not None:
            # 熔断期内不尝试；到期后放行一次探测
            if time.monotonic() - self._disabled_at < REDIS_RETRY_AFTER:
                return False
        return True

    def _get_client(self):
        if self._client is None:
            import redis  # 延迟导入：未启用缓存时不引入启动开销

            self._client = redis.Redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
        return self._client

    def _fail(self, exc: BaseException) -> None:
        """操作失败 → 进入熔断（只告警一次，避免刷日志）。"""
        if not self._warned:
            logger.warning("Redis 缓存不可用，已降级为不缓存：%s", exc)
            self._warned = True
        self._disabled_at = time.monotonic()

    def _ok(self) -> None:
        """操作成功 → 解除熔断。"""
        self._disabled_at = None

    # ---------------- 读写 ----------------

    def get(self, key: str) -> str | None:
        if not self.enabled():
            return None
        try:
            value = self._get_client().get(key)
        except Exception as exc:  # noqa: BLE001 - 缓存故障不影响主流程
            self._fail(exc)
            return None
        self._ok()
        return value

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if not self.enabled():
            return
        try:
            self._get_client().set(key, value, ex=ttl or settings.REDIS_CACHE_TTL)
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)
            return
        self._ok()

    def delete_prefix(self, prefix: str) -> int:
        """按前缀批量删除（用 SCAN 而非 KEYS，避免阻塞 Redis 单线程）。

        返回删除数量；未启用/失败时返回 0。
        """
        if not self.enabled():
            return 0
        try:
            client = self._get_client()
            deleted = 0
            for key in client.scan_iter(match=f"{prefix}*", count=500):
                client.delete(key)
                deleted += 1
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)
            return 0
        self._ok()
        return deleted


cache = _Cache()
