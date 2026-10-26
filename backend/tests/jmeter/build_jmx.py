#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMeter 测试计划生成器（纯标准库，无需第三方依赖）。

本脚本为「教师智能备课系统」生成 8 套可直接被 Apache JMeter 5.6 加载并运行的
.jmx 性能/压力测试计划，覆盖：登录鉴权、知识图谱、备课流水线、文档上传、
对话(SSE)、管理批量、混合负载、阶梯加压。

用法：
    python build_jmx.py          # 在当前目录生成 *.jmx + sample 数据
    python build_jmx.py --host 127.0.0.1 --port 18000

生成的计划默认指向 http://${host}:${port}，host/port 通过「用户定义变量」配置，
运行时可在 JMeter UI 中修改，或用 -Jhost= -Jport= 覆盖。
"""
from __future__ import annotations

import argparse
import os
import xml.sax.saxutils as su

API = "/api/v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "18000"
CONFIG = {"host": DEFAULT_HOST, "port": DEFAULT_PORT}


# --------------------------------------------------------------------------
# 极简 JMeter XML 构建器
# 每个节点：(tag, attrs, props, subs)
#   props : 预渲染的子元素字符串（stringProp / boolProp / intProp / elementProp ...）
#   subs  : 子节点列表（会被包进 <hashTree>）
# --------------------------------------------------------------------------
def sp(name: str, val: str) -> str:
    return f'<stringProp name="{name}">{su.escape(str(val))}</stringProp>'


def bp(name: str, val: bool) -> str:
    return f'<boolProp name="{name}">{str(val).lower()}</boolProp>'


def ip(name: str, val: int) -> str:
    return f'<intProp name="{name}">{val}</intProp>'


def elem_prop(name, etype, gui, cls, props):
    return (
        f'<elementProp name="{name}" elementType="{etype}" '
        f'guiclass="{gui}" testclass="{cls}" testname="{su.escape(name)}">'
        + "".join(props)
        + "</elementProp>"
    )


def node(tag, attrs, props=None, subs=None):
    return (tag, list(attrs), list(props or []), list(subs or []))


def render(n):
    tag, attrs, props, subs = n
    a = "".join(f' {k}="{v}"' for k, v in attrs)
    inner = "".join(props)
    if subs:
        sub_xml = "".join(render(s) for s in subs)
        return f"<{tag}{a}>{inner}<hashTree>{sub_xml}</hashTree></{tag}>"
    return f"<{tag}{a}>{inner}</{tag}>"


def http_arg(name, value, meta="="):
    return elem_prop(
        name or "",
        "Argument",
        "HTTPArgument",
        "Argument",
        [
            sp("Argument.name", name),
            sp("Argument.value", value),
            sp("Argument.metadata", meta),
            bp("HTTPArgument.always_encode", False),
            sp("HTTPArgument.decode_choice", "false"),
        ],
    )


def serialize(root):
    return render(root)


# --------------------------------------------------------------------------
# 复用构件
# --------------------------------------------------------------------------
def test_plan(name, comment, *thread_subs):
    tp = node(
        "TestPlan",
        [("guiclass", "TestPlanGui"), ("testclass", "TestPlan"),
         ("testname", name), ("enabled", "true")],
        [
            sp("TestPlan.comments", comment),
            bp("TestPlan.functional_mode", False),
            bp("TestPlan.tearDown_on_shutdown", True),
            bp("TestPlan.serialize_threadgroups", False),
            elem_prop(
                "TestPlan.user_defined_variables", "Arguments",
                "ArgumentsPanel", "Arguments",
                [sp("TestPlan.user_defined_variables", ""),
                 collection("Arguments.arguments", [
                     udv("host", CONFIG["host"]),
                     udv("port", CONFIG["port"]),
                     udv("teacher_email", "teacher@example.com"),
                     udv("teacher_pwd", "teacher123456"),
                     udv("admin_email", "admin@example.com"),
                     udv("admin_pwd", "admin123456"),
                     udv("chapter_id", "1"),
                 ])],
            ),
            sp("TestPlan.user_define_classpath", ""),
        ],
        list(thread_subs),
    )
    return node(
        "jmeterTestPlan",
        [("version", "1.2"), ("properties", "5.0"), ("jmeter", "5.6")],
        [],
        [tp],
    )


def udv(name, value):
    return elem_prop(
        name, "Argument", "GUI", "Argument",
        [sp("Argument.name", name), sp("Argument.value", value),
         sp("Argument.metadata", "=")],
    )


def collection(name, items):
    return f'<collectionProp name="{name}">{"".join(items)}</collectionProp>'


def thread_group(name, threads, ramp, loops=1, duration=0, subs=None):
    controller = elem_prop(
        "ThreadGroup.main_controller", "LoopController",
        "LoopControlPanel", "LoopController",
        [sp("ThreadGroup.main_controller", ""),
         bp("LoopController.continue_forever", False),
         ip("LoopController.loops", loops if duration == 0 else -1)],
    )
    props = [
        sp("ThreadGroup.on_sample_error", "continue"),
        controller,
        sp("ThreadGroup.num_threads", str(threads)),
        sp("ThreadGroup.ramp_time", str(ramp)),
        bp("ThreadGroup.scheduler", duration > 0),
        ip("ThreadGroup.duration", duration),
        ip("ThreadGroup.delay", 0),
    ]
    return node(
        "ThreadGroup",
        [("guiclass", "ThreadGroupGui"), ("testclass", "ThreadGroup"),
         ("testname", name), ("enabled", "true")],
        props,
        list(subs or []),
    )


def http_defaults():
    return node(
        "ConfigTestElement",
        [("guiclass", "HttpDefaultsGui"), ("testclass", "ConfigTestElement"),
         ("testname", "HTTP Request Defaults"), ("enabled", "true")],
        [
            collection("Arguments.arguments", [
                elem_prop("HTTPSampler.protocol", "Argument", "GUI", "Argument",
                          [sp("Argument.name", "HTTPSampler.protocol"),
                           sp("Argument.value", "http"), sp("Argument.metadata", "=")]),
                elem_prop("HTTPSampler.domain", "Argument", "GUI", "Argument",
                          [sp("Argument.name", "HTTPSampler.domain"),
                           sp("Argument.value", "${host}"), sp("Argument.metadata", "=")]),
                elem_prop("HTTPSampler.port", "Argument", "GUI", "Argument",
                          [sp("Argument.name", "HTTPSampler.port"),
                           sp("Argument.value", "${port}"), sp("Argument.metadata", "=")]),
                elem_prop("HTTPSampler.contentEncoding", "Argument", "GUI", "Argument",
                          [sp("Argument.name", "HTTPSampler.contentEncoding"),
                           sp("Argument.value", "UTF-8"), sp("Argument.metadata", "=")]),
                elem_prop("HTTPSampler.path", "Argument", "GUI", "Argument",
                          [sp("Argument.name", "HTTPSampler.path"),
                           sp("Argument.value", ""), sp("Argument.metadata", "=")]),
            ]),
        ],
    )


def header_manager(name, headers):
    items = [
        elem_prop("", "Header", "Header", "Header",
                  [sp("Header.name", k), sp("Header.value", v)])
        for k, v in headers.items()
    ]
    return node(
        "HeaderManager",
        [("guiclass", "HeaderPanel"), ("testclass", "HeaderManager"),
         ("testname", name), ("enabled", "true")],
        [collection("HeaderManager.headers", items)],
    )


def login_sampler(var_name="token"):
    """OAuth2 表单登录并提取 access_token。"""
    args = collection("Arguments.arguments", [
        http_arg("username", "${teacher_email}"),
        http_arg("password", "${teacher_pwd}"),
    ])
    sampler = node(
        "HTTPSamplerProxy",
        [("guiclass", "HttpTestSampleGui"), ("testclass", "HTTPSamplerProxy"),
         ("testname", "Login (get token)"), ("enabled", "true")],
        [
            sp("HTTPSampler.domain", "${host}"),
            sp("HTTPSampler.port", "${port}"),
            sp("HTTPSampler.protocol", "http"),
            sp("HTTPSampler.path", f"{API}/login/access-token"),
            sp("HTTPSampler.method", "POST"),
            sp("HTTPSampler.contentEncoding", "UTF-8"),
            sp("HTTPSampler.postBodyRaw", "false"),
            elem_prop("HTTPsampler.Arguments", "Arguments",
                      "HTTPArgumentsPanel", "Arguments",
                      [sp("HTTPsampler.Arguments", ""), args]),
            bp("HTTPSampler.follow_redirects", True),
            bp("HTTPSampler.use_keepalive", True),
            bp("HTTPSampler.use_multipart_post", False),
        ],
    )
    extractor = node(
        "JSONPostProcessor",
        [("guiclass", "JSONPostProcessorGui"), ("testclass", "JSONPostProcessor"),
         ("testname", "Extract access_token"), ("enabled", "true")],
        [
            sp("JSONPostProcessor.referenceNames", var_name),
            sp("JSONPostProcessor.jsonPathExprs", "$.access_token"),
            sp("JSONPostProcessor.match_numbers", "1"),
            sp("JSONPostProcessor.defaultValues", ""),
            sp("JSONPostProcessor.compute_concat", "false"),
        ],
    )
    return sampler, extractor


def api_get(name, path, token="${token}"):
    return http_sampler(name, "GET", path, token=token)


def api_post(name, path, body=None, token="${token}"):
    return http_sampler(name, "POST", path, body=body, token=token)


def http_sampler(name, method, path, body=None, token="${token}"):
    if body is not None:
        args = collection("Arguments.arguments", [
            http_arg("", body),
        ])
        arg_props = [sp("HTTPSampler.postBodyRaw", "true"),
                     elem_prop("HTTPsampler.Arguments", "Arguments",
                               "HTTPArgumentsPanel", "Arguments",
                               [sp("HTTPsampler.Arguments", ""), args])]
    else:
        arg_props = [sp("HTTPSampler.postBodyRaw", "false"),
                     elem_prop("HTTPsampler.Arguments", "Arguments",
                               "HTTPArgumentsPanel", "Arguments",
                               [sp("HTTPsampler.Arguments", ""),
                                collection("Arguments.arguments", [])])]
    return node(
        "HTTPSamplerProxy",
        [("guiclass", "HttpTestSampleGui"), ("testclass", "HTTPSamplerProxy"),
         ("testname", name), ("enabled", "true")],
        [
            sp("HTTPSampler.domain", "${host}"),
            sp("HTTPSampler.port", "${port}"),
            sp("HTTPSampler.protocol", "http"),
            sp("HTTPSampler.path", path),
            sp("HTTPSampler.method", method),
            sp("HTTPSampler.contentEncoding", "UTF-8"),
            bp("HTTPSampler.follow_redirects", True),
            bp("HTTPSampler.use_keepalive", True),
            bp("HTTPSampler.use_multipart_post", False),
        ] + arg_props,
    )


def constant_timer(millis=100):
    return node(
        "ConstantTimer",
        [("guiclass", "ConstantTimerGui"), ("testclass", "ConstantTimer"),
         ("testname", f"Think Time {millis}ms"), ("enabled", "true")],
        [sp("ConstantTimer.delay", str(millis))],
    )


def csv_users(filename="users.csv", var="email,pwd", threads=None):
    return node(
        "CSVDataSet",
        [("guiclass", "TestBeanGUI"), ("testclass", "CSVDataSet"),
         ("testname", "CSV Data Set (accounts)"), ("enabled", "true")],
        [
            sp("filename", filename),
            sp("fileEncoding", "UTF-8"),
            sp("variableNames", var),
            sp("delimiter", ","),
            sp("quotedData", "false"),
            bp("recycle", True),
            bp("stopThread", False),
            sp("shareMode", "shareMode.all"),
        ],
    )


def listeners(plan_name):
    base = os.path.splitext(plan_name)[0]
    tree = node(
        "ResultCollector",
        [("guiclass", "ViewResultsFullVisualizer"), ("testclass", "ResultCollector"),
         ("testname", "View Results Tree"), ("enabled", "true")],
        [sp("filename", f"results/{base}.jtl"),
         elem_prop("saveConfig", "SampleSaveConfiguration",
                   "HTTP", "SampleSaveConfiguration", [
                       bp("xml", True), bp("csv", False),
                       bp("responseData", False), bp("time", True),
                       bp("latency", True), bp("success", True),
                       bp("label", True), bp("code", True),
                       bp("message", True), bp("threadName", True)]),
         bp("ResultCollector.error_logging", False)],
    )
    agg = node(
        "ResultCollector",
        [("guiclass", "AggReport"), ("testclass", "AggregateReport"),
         ("testname", "Aggregate Report"), ("enabled", "true")],
        [sp("filename", f"results/{base}-agg.csv"),
         elem_prop("saveConfig", "SampleSaveConfiguration",
                   "HTTP", "SampleSaveConfiguration", [
                       bp("xml", False), bp("csv", True),
                       bp("time", True), bp("latency", True),
                       bp("success", True), bp("label", True),
                       bp("code", True)]),
         bp("ResultCollector.error_logging", False)],
    )
    summ = node(
        "ResultCollector",
        [("guiclass", "SummaryReport"), ("testclass", "SummaryReport"),
         ("testname", "Summary Report"), ("enabled", "true")],
        [sp("filename", f"results/{base}-summary.csv"),
         bp("ResultCollector.error_logging", False)],
    )
    return [tree, agg, summ]


# --------------------------------------------------------------------------
# 各测试计划
# --------------------------------------------------------------------------
def plan_login():
    lg, ex = login_sampler()
    test = thread_group(
        "Login Load", 50, 10, loops=10,
        subs=[http_defaults(), header_manager("Content-Type", {"Content-Type": "application/json"}),
              lg, ex, api_post("Test token", f"{API}/login/test-token"),
              constant_timer(200)] + listeners("01-auth-login"),
    )
    return test_plan("01 登录鉴权压测", "OAuth2 登录并校验 token 有效性", test)


def plan_kp():
    lg, ex = login_sampler()
    subs = [
        http_defaults(),
        header_manager("Auth+JSON", {"Content-Type": "application/json",
                                     "Authorization": "Bearer ${token}"}),
        lg, ex,
        api_get("图谱全量", f"{API}/knowledge-points/graph/full"),
        api_get("知识点列表", f"{API}/knowledge-points/"),
        api_get("子图(示例ID)", f"{API}/knowledge-points/1/subgraph"),
        api_post("章节上下文", f"{API}/knowledge-points/chapter-context",
                 '{"chapter_id": "${chapter_id}"}'),
        api_post("知识点检索", f"{API}/knowledge-points/search", '{"query": "光的反射"}'),
        constant_timer(150),
    ] + listeners("02-kp-list-graph")
    return test_plan("02 知识图谱读路径", "图谱/列表/子图/检索 核心读路径",
                     thread_group("KP Read", 50, 15, loops=10, subs=subs))


def plan_lp():
    lg, ex = login_sampler()
    subs = [
        http_defaults(),
        header_manager("Auth", {"Content-Type": "application/json",
                               "Authorization": "Bearer ${token}"}),
        lg, ex,
        api_get("备课列表", f"{API}/lesson-plans/"),
        api_post("创建备课", f"{API}/lesson-plans/",
                 '{"title": "测试备课${__threadNum}", "chapter_id": "${chapter_id}"}'),
        api_post("提交审批", f"{API}/lesson-plans/1/submit"),
        api_get("导出Word", f"{API}/lesson-plans/1/export"),
        constant_timer(200),
    ] + listeners("03-lesson-plan-crud")
    return test_plan("03 备课流水线", "备课 CRUD + 提交 + 导出 写路径",
                     thread_group("LessonPlan", 50, 15, loops=5, subs=subs))


def plan_doc():
    lg, ex = login_sampler()
    # 上传用 multipart；这里用文件上传采样器
    upload = node(
        "HTTPSamplerProxy",
        [("guiclass", "HttpTestSampleGui"), ("testclass", "HTTPSamplerProxy"),
         ("testname", "上传文档(示例txt)"), ("enabled", "true")],
        [
            sp("HTTPSampler.domain", "${host}"),
            sp("HTTPSampler.port", "${port}"),
            sp("HTTPSampler.protocol", "http"),
            sp("HTTPSampler.path", f"{API}/documents/upload"),
            sp("HTTPSampler.method", "POST"),
            sp("HTTPSampler.contentEncoding", "UTF-8"),
            bp("HTTPSampler.follow_redirects", True),
            bp("HTTPSampler.use_keepalive", True),
            bp("HTTPSampler.use_multipart_post", True),
            elem_prop("HTTPsampler.Files", "HTTPFileArgs", "HTTPFileArgs",
                      "HTTPFileArgs",
                      [collection("HTTPFileArgs.files", [
                          elem_prop("", "HTTPFileArg", "HTTPFileArg", "HTTPFileArg", [
                              sp("File.path", "sample.txt"),
                              sp("File.paramname", "file"),
                              sp("File.mimetype", "text/plain")])])]),
            elem_prop("HTTPsampler.Arguments", "Arguments",
                      "HTTPArgumentsPanel", "Arguments",
                      [sp("HTTPsampler.Arguments", ""),
                       collection("Arguments.arguments", [])]),
        ],
    )
    subs = [
        http_defaults(),
        header_manager("Auth", {"Authorization": "Bearer ${token}"}),
        lg, ex, upload,
        api_get("文档列表", f"{API}/documents/"),
        api_post("文档检索", f"{API}/documents/search", '{"query": "透镜"}'),
        constant_timer(300),
    ] + listeners("04-doc-upload")
    return test_plan("04 文档上传解析", "文档上传 + 列表 + 检索",
                     thread_group("DocUpload", 30, 15, loops=3, subs=subs))


def plan_chat():
    lg, ex = login_sampler()
    subs = [
        http_defaults(),
        header_manager("Auth+SSE", {"Content-Type": "application/json",
                                   "Accept": "text/event-stream",
                                   "Authorization": "Bearer ${token}"}),
        lg, ex,
        api_post("对话(SSE)", f"{API}/chat/",
                 '{"messages": [{"role": "user", "content": "请讲解光的反射定律"}]}'),
        constant_timer(500),
    ] + listeners("05-chat-sse")
    return test_plan("05 对话流式", "chat SSE 流式端点（LLM 绑定，延迟较高）",
                     thread_group("Chat", 20, 20, loops=2, subs=subs))


def plan_admin():
    lg, ex = login_sampler("admin_token")
    subs = [
        http_defaults(),
        header_manager("AdminAuth", {"Content-Type": "application/json",
                                    "Authorization": "Bearer ${admin_token}"}),
        # 用 admin 账号登录
        node("HTTPSamplerProxy",
             [("guiclass", "HttpTestSampleGui"), ("testclass", "HTTPSamplerProxy"),
              ("testname", "Admin Login"), ("enabled", "true")],
             [sp("HTTPSampler.domain", "${host}"), sp("HTTPSampler.port", "${port}"),
              sp("HTTPSampler.protocol", "http"),
              sp("HTTPSampler.path", f"{API}/login/access-token"),
              sp("HTTPSampler.method", "POST"), sp("HTTPSampler.contentEncoding", "UTF-8"),
              sp("HTTPSampler.postBodyRaw", "false"),
              elem_prop("HTTPsampler.Arguments", "Arguments", "HTTPArgumentsPanel",
                        "Arguments", [sp("HTTPsampler.Arguments", ""),
                                      collection("Arguments.arguments", [
                                          http_arg("username", "${admin_email}"),
                                          http_arg("password", "${admin_pwd}")])]),
              bp("HTTPSampler.use_keepalive", True)]),
        node("JSONPostProcessor",
             [("guiclass", "JSONPostProcessorGui"), ("testclass", "JSONPostProcessor"),
              ("testname", "Extract admin_token"), ("enabled", "true")],
             [sp("JSONPostProcessor.referenceNames", "admin_token"),
              sp("JSONPostProcessor.jsonPathExprs", "$.access_token"),
              sp("JSONPostProcessor.match_numbers", "1"),
              sp("JSONPostProcessor.defaultValues", "")]),
        api_get("统计看板", f"{API}/admin/stats"),
        api_get("候选队列", f"{API}/admin/candidates"),
        api_get("图谱质量", f"{API}/admin/graph-quality"),
        api_get("系统日志", f"{API}/admin/logs"),
        constant_timer(300),
    ] + listeners("06-admin-batch")
    return test_plan("06 管理端批量", "统计/候选/图谱质量/日志 重路径",
                     thread_group("Admin", 30, 15, loops=5, subs=subs))


def plan_mixed():
    lg, ex = login_sampler()
    common = [http_defaults(),
              header_manager("Auth", {"Content-Type": "application/json",
                                     "Authorization": "Bearer ${token}"}),
              lg, ex]
    # 通过吞吐量控制器配比业务
    def tc(name, pct, sampler):
        return node(
            "ThroughputController",
            [("guiclass", "ThroughputControllerGui"),
             ("testclass", "ThroughputController"),
             ("testname", name), ("enabled", "true")],
            [bp("ThroughputController.style", False),  # percent
             sp("ThroughputController.perThread", "true"),
             ip("ThroughputController.maxThroughput", pct)],
            [sampler, constant_timer(100)],
        )
    subs = common + [
        tc("read-KP", 40, api_get("图谱全量", f"{API}/knowledge-points/graph/full")),
        tc("list-LP", 30, api_get("备课列表", f"{API}/lesson-plans/")),
        tc("read-doc", 20, api_get("文档列表", f"{API}/documents/")),
        tc("admin-stats", 10, api_get("统计看板", f"{API}/admin/stats")),
    ] + listeners("07-mixed-load")
    return test_plan("07 混合业务负载", "按权重混合核心读/写路径",
                     thread_group("Mixed", 100, 30, loops=20, subs=subs))


def plan_stress():
    """阶梯加压：50→200→500，每级 5 分钟，观察拐点。"""
    lg, ex = login_sampler()
    subs = [
        http_defaults(),
        header_manager("Auth", {"Content-Type": "application/json",
                               "Authorization": "Bearer ${token}"}),
        lg, ex,
        api_get("健康探针", f"{API}/utils/health-check/"),
        api_get("图谱全量", f"{API}/knowledge-points/graph/full"),
        api_get("备课列表", f"{API}/lesson-plans/"),
        constant_timer(50),
    ] + listeners("08-stress-ramp")
    # 标准 ThreadGroup 用较大并发 + ramp 模拟加压；若已装 jp@gc 插件可换成
    # Ultimate Thread Group。此处用单一高并发组，注释说明替代方案。
    tg = thread_group("Stress Ramp", 500, 300, loops=1, duration=900, subs=subs)
    return test_plan("08 阶梯压力", "500 并发/15min 加压，定位错误率拐点",
                     tg)


PLANS = {
    "01-auth-login.jmx": plan_login,
    "02-kp-list-graph.jmx": plan_kp,
    "03-lesson-plan-crud.jmx": plan_lp,
    "04-doc-upload.jmx": plan_doc,
    "05-chat-sse.jmx": plan_chat,
    "06-admin-batch.jmx": plan_admin,
    "07-mixed-load.jmx": plan_mixed,
    "08-stress-ramp.jmx": plan_stress,
}


def write_sample_files(out_dir):
    with open(os.path.join(out_dir, "sample.txt"), "w", encoding="utf-8") as f:
        f.write("这是一份用于上传测试的示例教材文本。\n光的反射定律：反射光线、入射光线和法线在同一平面内。\n")
    with open(os.path.join(out_dir, "users.csv"), "w", encoding="utf-8") as f:
        f.write("email,pwd\n")
        f.write("teacher@example.com,teacher123456\n")
        f.write("admin@example.com,admin123456\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", default=DEFAULT_PORT)
    args = ap.parse_args()
    CONFIG["host"] = args.host
    CONFIG["port"] = args.port

    out_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(out_dir, "results"), exist_ok=True)
    write_sample_files(out_dir)

    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    for fname, builder in PLANS.items():
        xml = header + serialize(builder())
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"generated: {fname}")
    print(f"\n共生成 {len(PLANS)} 套 JMeter 计划于 {out_dir}")


if __name__ == "__main__":
    main()
