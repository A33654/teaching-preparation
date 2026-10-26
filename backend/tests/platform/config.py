#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试平台配置：环境参数 + 合格指标阈值（单一可信源）。

所有阈值集中在此，便于按环境调参；测试断言与报告仪表盘均从这里读取。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class EnvConfig:
    host: str = "127.0.0.1"
    port: int = 18000
    api_prefix: str = "/api/v1"
    # 是否用 Mock 替代外部依赖（Neo4j / LLM）。沙箱无全栈时为 True。
    mock_external: bool = True
    # 测试库：SQLite 文件路径（相对 backend 目录）
    sqlite_path: str = ":memory:"
    jmeter_bin: str = "jmeter"
    results_dir: str = "tests/platform/results"


@dataclass
class FunctionalThresholds:
    pass_rate_min: float = 95.0           # 用例通过率下限 %
    max_open_critical: int = 0           # 致命/严重缺陷未关闭数
    auth_semantics_ok: bool = True       # 401 vs 403 必须正确
    idempotency_required: bool = True    # 重复 name/提交需幂等


@dataclass
class PerformanceThresholds:
    read_p95_ms: int = 200               # 读路径 P95 @50并发
    write_p95_ms: int = 500              # 写路径 P95 @50并发
    read_error_rate: float = 0.1         # % 读错误率
    write_error_rate: float = 0.5        # % 写错误率
    ai_p95_ms: int = 30000              # AI 生成 P95
    ai_error_rate: float = 1.0
    stress_error_rate_max: float = 5.0   # 拐点错误率上限 %
    endurance_drift_pct: float = 10.0    # 耐力 1h 延迟漂移上限 %


@dataclass
class AIEvalThresholds:
    rubric_avg_min: float = 4.0          # 0-5 均分下限
    kp_coverage_min: float = 90.0        # 章节知识点覆盖率 %
    exam_coverage_min: float = 85.0      # 考纲覆盖 %
    max_prereq_breaks: int = 0           # 前置链断点
    sse_complete_rate: float = 100.0     # 流式事件完整率 %
    fallback_required: bool = True       # 单 Provider 失败需自动切换


@dataclass
class PlatformConfig:
    env: EnvConfig = field(default_factory=EnvConfig)
    functional: FunctionalThresholds = field(default_factory=FunctionalThresholds)
    performance: PerformanceThresholds = field(default_factory=PerformanceThresholds)
    ai_eval: AIEvalThresholds = field(default_factory=AIEvalThresholds)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def load(cls, path: str | None = None) -> "PlatformConfig":
        cfg = cls()
        if path and os.path.exists(path):
            import yaml  # 可选依赖
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            # 浅合并
            for section, model in (
                ("env", cfg.env), ("functional", cfg.functional),
                ("performance", cfg.performance), ("ai_eval", cfg.ai_eval),
            ):
                if section in data:
                    for k, v in data[section].items():
                        if hasattr(model, k):
                            setattr(model, k, v)
        # 环境变量覆盖
        if os.getenv("TEST_HOST"):
            cfg.env.host = os.getenv("TEST_HOST")
        if os.getenv("TEST_PORT"):
            cfg.env.port = int(os.getenv("TEST_PORT"))
        if os.getenv("TEST_MOCK_EXTERNAL"):
            cfg.env.mock_external = os.getenv("TEST_MOCK_EXTERNAL").lower() in ("1", "true", "yes")
        return cfg


# 模块级单例
CONFIG = PlatformConfig.load(os.path.join(os.path.dirname(__file__), "config.yaml"))
