#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML 报告仪表盘生成器（无第三方依赖）。

输入：runner 产出的结果字典（results.json 同结构）。
输出：单文件 HTML 仪表盘，含概览卡片、各测试层明细、合格指标核验、趋势占位。
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


LIGHT_CSS = """
:root{
  --bg:#f5f7fa; --card:#ffffff; --ink:#1f2933; --muted:#647084;
  --line:#e3e8ef; --ok:#1f9d55; --warn:#d9822b; --bad:#e0483e; --accent:#2f6fed;
}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);font-size:14px;line-height:1.6}
header{background:linear-gradient(120deg,#2f6fed,#5b8def);color:#fff;padding:22px 28px}
header h1{margin:0;font-size:20px}
header .sub{opacity:.9;font-size:12px;margin-top:4px}
.wrap{max-width:1080px;margin:0 auto;padding:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card .k{font-size:12px;color:var(--muted)}
.card .v{font-size:26px;font-weight:700;margin-top:4px}
.card .v.ok{color:var(--ok)} .card .v.warn{color:var(--warn)} .card .v.bad{color:var(--bad)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:14px 0}
section h2{margin:0 0 12px;font-size:16px;border-left:4px solid var(--accent);padding-left:10px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
.badge.pass{background:#e6f6ec;color:var(--ok)}
.badge.fail{background:#fdecea;color:var(--bad)}
.badge.partial{background:#fef3e2;color:var(--warn)}
.badge.na{background:#eef1f5;color:var(--muted)}
.bar{height:8px;background:#eef1f5;border-radius:6px;overflow:hidden}
.bar > i{display:block;height:100%;background:var(--accent)}
.checklist li{margin:6px 0}
footer{color:var(--muted);font-size:12px;text-align:center;padding:18px}
"""


def _badge(status: str) -> str:
    label = {"pass": "通过", "fail": "未通过", "partial": "部分通过", "na": "无数据"}.get(status, status)
    return f'<span class="badge {status}">{label}</span>'


def _pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def render(results: dict[str, Any]) -> str:
    env = results.get("environment", {})
    suites = results.get("suites", {})
    overall = results.get("overall_status", "na")

    # ---- 概览卡片 ----
    total_t = sum(s.get("total", 0) for s in suites.values() if isinstance(s, dict) and "total" in s)
    total_p = sum(s.get("passed", 0) for s in suites.values() if isinstance(s, dict) and "total" in s)
    overall_rate = _pct(total_p, total_t)
    rate_cls = "ok" if overall_rate >= 95 else ("warn" if overall_rate >= 80 else "bad")

    cards = f"""
    <div class="cards">
      <div class="card"><div class="k">总体状态</div><div class="v {overall}">{_badge(overall)}</div></div>
      <div class="card"><div class="k">用例总数</div><div class="v">{total_t}</div></div>
      <div class="card"><div class="k">通过率</div><div class="v {rate_cls}">{overall_rate}%</div></div>
      <div class="card"><div class="k">AI 评测均分</div><div class="v">{suites.get('ai_eval',{}).get('rubric_avg','-')}</div></div>
      <div class="card"><div class="k">性能场景</div><div class="v">{len(suites.get('performance',{}).get('scenarios',[]))}</div></div>
    </div>"""

    body = []

    # ---- 功能/单元/接口套件 ----
    for key in ("unit", "api"):
        s = suites.get(key)
        if not s:
            continue
        rate = _pct(s.get("passed", 0), s.get("total", 0))
        rows = "".join(
            f"<tr><td>{html.escape(str(d.get('name','')))}</td>"
            f"<td>{html.escape(str(d.get('outcome','')))}</td>"
            f"<td>{html.escape(str(d.get('detail',''))[:120])}</td></tr>"
            for d in s.get("details", [])[:50]
        )
        body.append(f"""
        <section><h2>{ '单元测试 (L0)' if key=='unit' else '接口功能 (L1)' }</h2>
          <p>通过率 <b>{rate}%</b> · 总计 {s.get('total',0)} · 通过 {s.get('passed',0)} · 失败 {s.get('failed',0)} · 错误 {s.get('error',0)} {_badge(s.get('status','na'))}</p>
          <div class="bar"><i style="width:{rate}%"></i></div>
          <table><thead><tr><th>用例</th><th>结果</th><th>说明</th></tr></thead><tbody>{rows}</tbody></table>
        </section>""")

    # ---- AI 评测 ----
    ae = suites.get("ai_eval")
    if ae:
        thr = results.get("thresholds", {}).get("ai_eval", {})
        rows = "".join(
            f"<tr><td>{html.escape(str(c.get('name','')))}</td>"
            f"<td>{html.escape(str(c.get('rubric','')))}</td>"
            f"<td>{html.escape(str(c.get('coverage','')))}%</td>"
            f"<td>{_badge(c.get('status','na'))}</td></tr>"
            for c in ae.get("cases", [])
        )
        body.append(f"""
        <section><h2>AI 评测 (L3)</h2>
          <p>rubric 均分 <b>{ae.get('rubric_avg','-')}</b> (合格线 {thr.get('rubric_avg_min','-')}) ·
             知识点覆盖率 <b>{ae.get('kp_coverage','-')}%</b> · 前置断点 <b>{ae.get('prereq_breaks',0)}</b> ·
             流式完整率 <b>{ae.get('sse_complete_rate','-')}%</b> {_badge(ae.get('status','na'))}</p>
          <table><thead><tr><th>评测用例</th><th>rubric</th><th>覆盖%</th><th>状态</th></tr></thead><tbody>{rows}</tbody></table>
        </section>""")

    # ---- 性能/压力 ----
    perf = suites.get("performance")
    if perf and perf.get("scenarios"):
        rows = "".join(
            f"<tr><td>{html.escape(str(s.get('name','')))}</td>"
            f"<td>{s.get('concurrency','-')}</td>"
            f"<td>{s.get('p95_ms','-')} ms</td>"
            f"<td>{s.get('tps','-')}</td>"
            f"<td>{s.get('error_rate','-')}%</td>"
            f"<td>{_badge(s.get('status','na'))}</td></tr>"
            for s in perf["scenarios"]
        )
        body.append(f"""
        <section><h2>性能与压力 (L2 · JMeter)</h2>
          <table><thead><tr><th>场景</th><th>并发</th><th>P95</th><th>TPS</th><th>错误率</th><th>状态</th></tr></thead><tbody>{rows}</tbody></table>
          <p class="badge na">说明：需 Java17+JMeter 运行 .jmx 后回填结果</p>
        </section>""")

    # ---- 合格指标核验 ----
    checks = results.get("acceptance", [])
    if checks:
        items = "".join(
            f"<li>{_badge(c.get('status','na'))} {html.escape(str(c.get('metric','')))} — {html.escape(str(c.get('value','')))} "
            f"(合格线 {html.escape(str(c.get('target','')))}): {html.escape(str(c.get('note','')))}</li>"
            for c in checks
        )
        body.append(f"<section><h2>合格指标核验</h2><ul class='checklist'>{items}</ul></section>")

    html_doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>测试自动化平台 · 报告</title><style>{LIGHT_CSS}</style></head>
<body><header><h1>教师智能备课系统 · 测试报告</h1>
<div class="sub">生成时间 {html.escape(str(results.get('generated_at','')))} · 环境 {html.escape(str(env.get('host','')))}:{env.get('port','')} · mock_external={env.get('mock_external','')}</div></header>
<div class="wrap">{cards}{''.join(body)}</div>
<footer>由自建测试自动化平台生成 · 数据源 results.json</footer></body></html>"""
    return html_doc


def write_report(results: dict[str, Any], out_path: str) -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(results), encoding="utf-8")
    # 同时写结构化 JSON
    (out.parent / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(out)
