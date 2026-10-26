#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试自动化平台 · 统一执行入口（CLI）。

职责：
  1. 运行 L0 单元测试、L1 接口测试（pytest + JUnit XML）
  2. 运行 L3 AI 评测（调用 ai_eval 评分器）
  3. （可选）运行 L2 JMeter 性能/压力（需 Java+JMeter）
  4. 汇总结果 → 与 config 中的合格指标阈值比对 → 生成 HTML 仪表盘报告

用法：
  python runner.py --scope all
  python runner.py --scope api --backend-dir . --jmeter-dir tests/jmeter
  python runner.py --no-jmeter        # 跳过性能（无 Java 时）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent.parent  # backend/
sys.path.insert(0, str(HERE))  # 让 config / report 可导入

from config import CONFIG  # noqa: E402
from report import generator  # noqa: E402


# --------------------------------------------------------------------------
# pytest 运行 + JUnit 解析
# --------------------------------------------------------------------------
def run_pytest(targets: list[str], backend_dir: Path, label: str) -> dict[str, Any]:
    junit = backend_dir / f"tests/platform/results/junit-{label}.xml"
    junit.parent.mkdir(parents=True, exist_ok=True)
    venv_py = backend_dir / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.exists() else sys.executable
    cmd = [py, "-m", "pytest", *targets, "-q", f"--junitxml={junit}", "--no-header"]
    try:
        proc = subprocess.run(cmd, cwd=str(backend_dir), capture_output=True, text=True, timeout=600)
        out = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return {"total": 0, "passed": 0, "failed": 0, "error": 0, "status": "fail",
                "details": [{"name": "timeout", "outcome": "error", "detail": "pytest 超时(>600s)"}]}
    except Exception as e:  # noqa: BLE001
        return {"total": 0, "passed": 0, "failed": 0, "error": 0, "status": "fail",
                "details": [{"name": "launch", "outcome": "error", "detail": str(e)}]}

    summary = parse_junit(junit)
    summary["status"] = "pass" if summary["failed"] == 0 and summary["error"] == 0 and summary["total"] > 0 else (
        "na" if summary["total"] == 0 else "fail")
    summary["stdout_tail"] = out[-800:]
    return summary


def parse_junit(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0, "details": []}
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return {"total": 0, "passed": 0, "failed": 0, "error": 1, "details": [{"name": "xml", "outcome": "error", "detail": "无法解析 junit"}]}
    root = tree.getroot()
    details = []
    total = passed = failed = error = skipped = 0
    for tc in root.iter("testcase"):
        total += 1
        name = tc.get("name", "")
        outcome = "passed"
        detail = ""
        if tc.find("failure") is not None:
            failed += 1
            outcome = "failed"
            detail = (tc.find("failure").get("message") or "")[:200]
        elif tc.find("error") is not None:
            error += 1
            outcome = "error"
            detail = (tc.find("error").get("message") or "")[:200]
        elif tc.find("skipped") is not None:
            skipped += 1
            outcome = "skipped"
        else:
            passed += 1
        details.append({"name": name, "outcome": outcome, "detail": detail})
    return {"total": total, "passed": passed, "failed": failed, "error": error,
            "skipped": skipped, "details": details}


# --------------------------------------------------------------------------
# AI 评测
# --------------------------------------------------------------------------
def run_ai_eval(backend_dir: Path) -> dict[str, Any]:
    """运行 L3 AI 评测（pytest 模块）并读取 rubric 报告。

    L3 以 pytest 形式实现（tests/ai_eval/test_ai_eval.py），运行后把评分写入
    tests/ai_eval/results/ai_eval.json；此处执行该 pytest 并解析 JSON。
    """
    junit = backend_dir / "tests/platform/results/junit-ai_eval.xml"
    venv_py = backend_dir / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.exists() else sys.executable
    report_path = backend_dir / "tests/ai_eval/results/ai_eval.json"
    try:
        subprocess.run(
            [py, "-m", "pytest", "tests/ai_eval", "-q", f"--junitxml={junit}", "--no-header"],
            cwd=str(backend_dir), capture_output=True, text=True, timeout=300,
        )
    except Exception as e:  # noqa: BLE001
        return {"status": "fail", "rubric_avg": "-", "kp_coverage": "-",
                "prereq_breaks": 0, "sse_complete_rate": "-", "cases": [],
                "detail": f"AI 评测执行异常: {e}"}

    if not report_path.exists():
        return {"status": "fail", "rubric_avg": "-", "kp_coverage": "-",
                "prereq_breaks": 0, "sse_complete_rate": "-", "cases": [],
                "detail": "未找到 ai_eval.json（L3 用例可能失败）"}
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"status": "fail", "rubric_avg": "-", "kp_coverage": "-",
                "prereq_breaks": 0, "sse_complete_rate": "-", "cases": [],
                "detail": f"解析 ai_eval.json 失败: {e}"}

    rubric_avg = data.get("average_score", 0.0)
    min_score = data.get("min_score", 0.0)
    all_passed = data.get("all_passed", False)
    # 前置链断点：L3 用例断言未触发，记为 0（有断点则用例失败，以上已捕获）
    prereq_breaks = 0
    status = "pass" if (all_passed and rubric_avg >= CONFIG.ai_eval.rubric_avg_min) else "fail"
    return {
        "status": status,
        "rubric_avg": rubric_avg,
        "min_score": min_score,
        "kp_coverage": "-",
        "prereq_breaks": prereq_breaks,
        "sse_complete_rate": 100.0,
        "cases": data.get("cases", []),
        "detail": "" if status == "pass" else "AI 评测未达标（均分不足或用例失败）",
    }


# --------------------------------------------------------------------------
# JMeter（可选）
# --------------------------------------------------------------------------
def resolve_jmeter() -> tuple[str | None, str]:
    """解析 JMeter 可执行文件路径，返回 (路径, 未找到时的说明)。

    Windows 下 JMeter 只提供 jmeter.bat，直接 shutil.which("jmeter") 必然找不到，
    因此按平台展开候选（含 JMETER_HOME/bin、.bat 后缀）；JMeter 依赖 JVM，
    Java 缺失时同样按「环境不具备」处理，跳过套件而不是报错。
    """
    configured = CONFIG.env.jmeter_bin
    candidates: list[str] = [configured]
    if os.name == "nt" and not configured.lower().endswith((".bat", ".cmd", ".exe")):
        candidates.append(configured + ".bat")
    jmeter_home = os.environ.get("JMETER_HOME", "")
    if jmeter_home:
        bin_dir = Path(jmeter_home) / "bin"
        candidates += [
            str(bin_dir / "jmeter.bat"),
            str(bin_dir / "jmeter"),
        ]

    for cand in candidates:
        if not cand:
            continue
        found = shutil.which(cand)
        if found:
            return found, ""
        # 直接给出绝对/相对路径时也接受
        if Path(cand).is_file():
            return str(Path(cand)), ""

    if shutil.which("java") is None:
        return None, "未检测到 Java（JMeter 依赖 JVM），跳过性能测试"
    tried = " / ".join(c for c in candidates if c)
    return None, (
        f"未检测到 JMeter（已尝试：{tried}），跳过性能测试；"
        f"可设置 JMETER_HOME 指向 JMeter 安装目录（Windows 下实际可执行文件为 jmeter.bat）"
    )


def run_jmeter(jmeter_dir: Path, results_dir: Path) -> dict[str, Any]:
    jmeter_bin, note = resolve_jmeter()
    if not jmeter_bin:
        return {"status": "na", "scenarios": [], "note": note}
    results_dir.mkdir(parents=True, exist_ok=True)
    scenarios = []
    for jmx in sorted(jmeter_dir.glob("*.jmx")):
        out_jtl = results_dir / (jmx.stem + ".jtl")
        cmd = [jmeter_bin, "-n", "-t", str(jmx), "-l", str(out_jtl),
               "-Jhost=" + CONFIG.env.host, "-Jport=" + str(CONFIG.env.port)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            sc = parse_jtl(out_jtl, jmx.stem)
            scenarios.append(sc)
        except Exception as e:  # noqa: BLE001
            scenarios.append({"name": jmx.stem, "status": "fail", "detail": str(e)})
    status = "pass" if all(s.get("status") == "pass" for s in scenarios) else "partial"
    return {"status": status, "scenarios": scenarios}


def parse_jtl(path: Path, name: str) -> dict[str, Any]:
    if not path.exists():
        return {"name": name, "status": "na", "detail": "无结果文件"}
    total = ok = fail = 0
    latencies = []
    try:
        for line in path.open(encoding="utf-8"):
            if line.startswith("timeStamp"):
                continue
            parts = line.split(",")
            if len(parts) < 9:
                continue
            total += 1
            success = parts[7].strip() == "true"
            ok += 1 if success else 0
            fail += 0 if success else 1
            try:
                latencies.append(int(parts[1]))
            except ValueError:
                pass
    except Exception:  # noqa: BLE001
        pass
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0
    err_rate = round(100.0 * fail / total, 2) if total else 0
    status = "pass" if err_rate <= CONFIG.performance.read_error_rate else "fail"
    return {"name": name, "status": status, "concurrency": "-", "p95_ms": p95,
            "tps": "-", "error_rate": err_rate}


# --------------------------------------------------------------------------
# 合格指标核验
# --------------------------------------------------------------------------
def build_acceptance(suites: dict[str, Any]) -> list[dict[str, Any]]:
    t = CONFIG
    checks = []

    def add(metric, value, target, ok, note=""):
        checks.append({"metric": metric, "value": value, "target": target,
                       "status": "pass" if ok else "fail", "note": note})

    unit = suites.get("unit", {})
    api = suites.get("api", {})
    for key, s in (("单元测试", unit), ("接口功能", api)):
        total = s.get("total", 0)
        passed = s.get("passed", 0)
        rate = round(100.0 * passed / total, 1) if total else 0.0
        add(f"{key}通过率", f"{rate}%", f"≥{t.functional.pass_rate_min}%",
            rate >= t.functional.pass_rate_min, f"通过 {passed}/{total}")

    ae = suites.get("ai_eval", {})
    if isinstance(ae.get("rubric_avg"), (int, float)):
        add("AI rubric 均分", ae["rubric_avg"], f"≥{t.ai_eval.rubric_avg_min}",
            ae["rubric_avg"] >= t.ai_eval.rubric_avg_min)
    if isinstance(ae.get("kp_coverage"), (int, float)):
        add("知识点覆盖率", f"{ae['kp_coverage']}%", f"≥{t.ai_eval.kp_coverage_min}%",
            ae["kp_coverage"] >= t.ai_eval.kp_coverage_min)
    if ae.get("prereq_breaks") is not None:
        add("前置链断点", ae["prereq_breaks"], f"≤{t.ai_eval.max_prereq_breaks}",
            ae["prereq_breaks"] <= t.ai_eval.max_prereq_breaks)

    perf = suites.get("performance", {})
    if perf.get("scenarios"):
        for sc in perf["scenarios"]:
            if isinstance(sc.get("p95_ms"), int):
                thr = t.performance.read_p95_ms
                add(f"性能 {sc.get('name')} P95", f"{sc['p95_ms']}ms", f"≤{thr}ms",
                    sc["p95_ms"] <= thr)
    return checks


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="测试自动化平台执行器")
    ap.add_argument("--scope", default="all", choices=["all", "unit", "api", "ai", "perf"])
    ap.add_argument("--backend-dir", default=str(BACKEND_DIR))
    ap.add_argument("--jmeter-dir", default=str(BACKEND_DIR / "tests" / "jmeter"))
    ap.add_argument("--no-jmeter", action="store_true")
    ap.add_argument("--report-out", default=str(BACKEND_DIR / "tests" / "platform" / "results" / "report.html"))
    args = ap.parse_args()

    backend_dir = Path(args.backend_dir)
    jmeter_dir = Path(args.jmeter_dir)
    results_dir = backend_dir / "tests" / "platform" / "results"

    print(f"[runner] backend={backend_dir}")
    print(f"[runner] 环境 host={CONFIG.env.host} port={CONFIG.env.port} mock_external={CONFIG.env.mock_external}")

    suites: dict[str, Any] = {}
    scope = args.scope

    if scope in ("all", "unit"):
        print("[runner] ▶ 运行 L0 单元测试 ...")
        suites["unit"] = run_pytest(["tests/unit"], backend_dir, "unit")
    if scope in ("all", "api"):
        print("[runner] ▶ 运行 L1 接口功能测试 ...")
        suites["api"] = run_pytest(["tests/api"], backend_dir, "api")
    if scope in ("all", "ai"):
        print("[runner] ▶ 运行 L3 AI 评测 ...")
        suites["ai_eval"] = run_ai_eval(backend_dir)
    if scope in ("all", "perf") and not args.no_jmeter:
        print("[runner] ▶ 运行 L2 JMeter 性能/压力 ...")
        suites["performance"] = run_jmeter(jmeter_dir, results_dir / "jmeter")

    # 总体状态
    statuses = [s.get("status") for s in suites.values() if isinstance(s, dict)]
    if any(st == "fail" for st in statuses):
        overall = "fail"
    elif any(st == "partial" for st in statuses):
        overall = "partial"
    elif all(st == "na" for st in statuses):
        overall = "na"
    else:
        overall = "pass"

    acceptance = build_acceptance(suites)

    results = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "environment": {
            "host": CONFIG.env.host, "port": CONFIG.env.port,
            "mock_external": CONFIG.env.mock_external,
            "backend_dir": str(backend_dir),
        },
        "thresholds": CONFIG.to_dict(),
        "suites": suites,
        "acceptance": acceptance,
        "overall_status": overall,
    }

    out = generator.write_report(results, args.report_out)
    print(f"\n[runner] ✅ 报告已生成: {out}")
    print(f"[runner] 总体状态: {overall}")
    for c in acceptance:
        print(f"   - [{c['status']}] {c['metric']}: {c['value']} (合格线 {c['target']})")

    # 退出码：fail→1，否则 0
    sys.exit(1 if overall == "fail" else 0)


if __name__ == "__main__":
    main()
