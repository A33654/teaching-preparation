# -*- coding: utf-8 -*-
"""轻量性能冒烟（脚本化压测，替代 JMeter 的可选项）。

背景：tests/jmeter/*.jmx 与本机 JMeter 5.6.3 的 xstream 解析器不兼容
（HeaderManager / HTTPSamplerProxy 反序列化失败），在修好 jmx 之前，
用本脚本对关键接口做并发压测，输出 P50/P95/P99、错误率与 TPS，
校验 tests/platform/config.yaml 中的性能阈值（读 ≤200ms、写 ≤500ms）。

用法（需先启动后端）：
    python tests/perf/perf_smoke.py --host 127.0.0.1 --port 18000 --total 200 --concurrency 50
"""
from __future__ import annotations

import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

READ_P95_MS = 200
WRITE_P95_MS = 500


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, int(round(len(sorted_vals) * pct)) - 1))
    return sorted_vals[idx]


def run_case(name: str, kind: str, fn, total: int, concurrency: int) -> dict:
    lat: list[float] = []
    errors = 0
    codes: dict[int, int] = {}
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(fn) for _ in range(total)]
        for f in futures:
            ms, ok, code = f.result()
            lat.append(ms)
            codes[code] = codes.get(code, 0) + 1
            if not ok:
                errors += 1
    duration = time.perf_counter() - start
    lat.sort()
    threshold = WRITE_P95_MS if kind == "write" else READ_P95_MS
    p95 = _percentile(lat, 0.95)
    return {
        "name": name,
        "kind": kind,
        "total": total,
        "concurrency": concurrency,
        "avg_ms": round(statistics.fmean(lat), 1) if lat else 0.0,
        "p50_ms": round(_percentile(lat, 0.50), 1),
        "p95_ms": round(p95, 1),
        "p99_ms": round(_percentile(lat, 0.99), 1),
        "max_ms": round(lat[-1], 1) if lat else 0.0,
        "error_rate": round(100.0 * errors / total, 2) if total else 0.0,
        "tps": round(total / duration, 1) if duration else 0.0,
        "threshold_ms": threshold,
        "passed": p95 <= threshold and errors == 0,
        "codes": codes,
    }


def _call(client: httpx.Client, method: str, url: str, **kw) -> tuple[float, bool, int]:
    t0 = time.perf_counter()
    try:
        r = client.request(method, url, timeout=30, **kw)
        return (time.perf_counter() - t0) * 1000, r.status_code < 400, r.status_code
    except Exception:
        return (time.perf_counter() - t0) * 1000, False, 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default=18000, type=int)
    ap.add_argument("--email", default="teacher@example.com")
    ap.add_argument("--password", default="teacher123456")
    ap.add_argument("--total", default=200, type=int)
    ap.add_argument("--concurrency", default=50, type=int)
    args = ap.parse_args()

    base = f"http://{args.host}:{args.port}/api/v1"
    with httpx.Client() as c:
        r = c.post(
            base + "/login/access-token",
            data={"username": args.email, "password": args.password},
            timeout=20,
        )
        r.raise_for_status()
        token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def make(method: str, path: str, kind: str, **kw):
        def _fn():
            with httpx.Client() as c:
                return _call(c, method, base + path, headers=headers, **kw)

        return _fn

    cases = [
        ("登录获取令牌", "write", make("POST", "/login/access-token", "write",
                                       data={"username": args.email, "password": args.password})),
        ("读取当前用户", "read", make("GET", "/users/me", "read")),
        ("教案列表", "read", make("GET", "/lesson-plans/?limit=20", "read")),
        ("作业列表", "read", make("GET", "/homework/?limit=20", "read")),
        ("知识点列表", "read", make("GET", "/knowledge-points/?limit=20", "read")),
        ("学科列表", "read", make("GET", "/curriculum/subjects", "read")),
        ("提醒-课程表", "read", make("GET", "/reminders/schedules", "read")),
    ]

    print(f"压测目标 {base} | 并发 {args.concurrency} | 每接口 {args.total} 次")
    print(f"{'场景':<12}{'类型':<6}{'平均':>9}{'P50':>9}{'P95':>9}{'P99':>9}{'错误率':>9}{'TPS':>9}  判定")
    print("-" * 88)
    rows = []
    for name, kind, fn in cases:
        res = run_case(name, kind, fn, args.total, args.concurrency)
        rows.append(res)
        flag = "PASS" if res["passed"] else "FAIL"
        print(
            f"{res['name']:<12}{res['kind']:<6}{res['avg_ms']:>9.1f}{res['p50_ms']:>9.1f}"
            f"{res['p95_ms']:>9.1f}{res['p99_ms']:>9.1f}{res['error_rate']:>8.1f}%{res['tps']:>9.1f}  {flag}"
            f"  (阈值 {res['threshold_ms']}ms)"
        )
    failed = [r for r in rows if not r["passed"]]
    print("-" * 88)
    print(f"合计 {len(rows)} 个场景，未达标 {len(failed)} 个")
    for r in failed:
        print(f"  - {r['name']}: P95 {r['p95_ms']}ms > {r['threshold_ms']}ms，错误率 {r['error_rate']}%，状态码分布 {r['codes']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
