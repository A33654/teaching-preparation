"""教案生成图：图谱上下文收集 → LLM 生成结构化教案。

上下文收集节点从 Neo4j 读取选中知识点及其前置/邻居，
让生成的教案体现知识脉络（前置知识回顾、关联延伸）。
"""
from app.agent.llm import get_structured_model
from app.agent.schemas import LessonPlanOutput
from app.agent.state import LessonPlanState
from app.knowledge_graph import KnowledgeGraphRepository
from langgraph.graph import END, START, StateGraph

LESSON_PLAN_PROMPT = """你是资深教研员，请根据提供的知识点及其知识图谱上下文，生成一份完整教案。

知识点及图谱上下文：
{graph_context}

教案要求：
- 教学目标分条列出（知识目标/能力目标/素养目标）
- 教学过程详细具体，包含：导入、新知讲解、例题精讲、课堂练习、总结归纳，每个环节注明时间分配（45分钟课）
- 若知识点有前置知识，教学过程需包含「复习回顾」环节
- 若提供考点（考纲要求），教学与例题必须覆盖对应层次的考查要求（了解/理解/掌握）
- 若提供学生常见误区/易错点，须在教学中设置「易错点辨析」环节针对性讲解纠正
- 学段：{grade_level}；学科：{subject}
- 附加要求：{requirements}
- 风格：{style}"""


def _collect_context(state: LessonPlanState) -> dict:
    """节点1：从 Neo4j 收集选中知识点及其图谱上下文（含考点考纲要求与常见误区）"""
    repo = KnowledgeGraphRepository()
    context: list[dict] = []

    for kp_id in state["knowledge_point_ids"][:10]:
        kp = repo.get_knowledge_point(kp_id)
        if not kp:
            continue
        prereqs = repo.get_prerequisites(kp_id)
        neighbors = repo.get_neighbors(kp_id, depth=1)
        try:
            exam_points = repo.get_exam_points(kp_id)
        except Exception:
            exam_points = []
        try:
            misconceptions = repo.get_misconceptions(kp_id)
        except Exception:
            misconceptions = []
        context.append(
            {
                "name": kp["name"],
                "description": kp["description"],
                "subject": kp["subject"],
                "prerequisites": [p["name"] for p in prereqs],
                "related": [n["name"] for n in neighbors if n["id"] != kp_id][:5],
                "exam_points": exam_points,
                "misconceptions": misconceptions,
            }
        )
    return {"graph_context": context}


def _generate(state: LessonPlanState) -> dict:
    """节点2：LLM 生成结构化教案"""
    context_lines = []
    for ctx in state["graph_context"]:
        line = f"- {ctx['name']}（{ctx['subject']}）：{ctx['description']}"
        if ctx["prerequisites"]:
            line += f"；前置知识：{'、'.join(ctx['prerequisites'])}"
        if ctx["related"]:
            line += f"；相关知识：{'、'.join(ctx['related'])}"
        exam_points = ctx.get("exam_points") or []
        if exam_points:
            line += (
                f"；考点（考纲要求）："
                + "、".join(
                    f"{e['name']}（{e.get('level', '理解')}）"
                    + (f": {e.get('description', '')}" if e.get("description") else "")
                    for e in exam_points
                )
            )
        misconceptions = ctx.get("misconceptions") or []
        if misconceptions:
            line += (
                f"；学生常见误区/易错点："
                + "、".join(
                    m.get("content", "")
                    + (f"（纠正：{m.get('correction')}）" if m.get("correction") else "")
                    for m in misconceptions
                )
            )
        context_lines.append(line)

    # RAG 教材素材片段
    material_lines = []
    for m in state.get("materials") or []:
        material_lines.append(f"- 【{m['filename']}】匹配「{m['keyword']}」：{m['snippet']}")

    prompt = LESSON_PLAN_PROMPT.format(
        graph_context="\n".join(context_lines) if context_lines else "（未提供图谱上下文）",
        grade_level=state["grade_level"] or "初中",
        subject=state["subject"] or "通用",
        requirements=state["requirements"] or "无",
        style=state["style"] or "标准",
    )
    if material_lines:
        prompt += "\n\n教材原文素材（RAG 检索补充，可参考其中表述，勿照抄整段）：\n" + "\n".join(material_lines)

    try:
        result: LessonPlanOutput = get_structured_model(
            LessonPlanOutput, temperature=0.7, max_tokens=4000
        ).invoke(prompt)
        grade = result.grade_level
        clean_grade = None
        for g in ("小学", "初中", "高中"):
            if g in grade:
                clean_grade = g
                break
        return {
            "lesson_plan": {
                "title": result.title,
                "subject": result.subject or state["subject"],
                "grade_level": clean_grade or state["grade_level"],
                "teaching_objectives": result.teaching_objectives,
                "teaching_process": result.teaching_process,
                "key_points": result.key_points,
                "difficult_points": result.difficult_points,
            }
        }
    except Exception as e:
        return {"error": f"教案生成失败: {e}"}


def _retrieve_materials(state: LessonPlanState) -> dict:
    """节点2：RAG 检索教材原文素材（PG Document 全文匹配章节名/知识点名）。

    固定流水线中的教材素材补充环节——教师上传的文档抽取后的原文
    按关键词检索片段，作为教案生成的补充材料。
    """
    from sqlmodel import Session, select

    from app.core.db import engine
    from app.models import Document

    keywords = {state.get("chapter", "")}
    for ctx in state["graph_context"]:
        keywords.add(ctx["name"])
    keywords = {k for k in keywords if k}

    materials: list[dict] = []
    if keywords:
        with Session(engine) as session:
            docs = session.exec(
                select(Document).where(
                    Document.extracted_text.is_not(None),
                    Document.status == "completed",
                )
            ).all()
            for doc in docs:
                text = doc.extracted_text or ""
                for kw in keywords:
                    pos = text.find(kw)
                    if pos >= 0:
                        materials.append(
                            {
                                "filename": doc.original_filename or doc.filename,
                                "snippet": text[max(0, pos - 100): pos + 300],
                                "keyword": kw,
                            }
                        )
                        break
    return {"materials": materials[:5]}


def _verify_plan(state: LessonPlanState) -> dict:
    """节点4：知识点校验（规则实现，不调 LLM，稳定可控）。

    比对教案初稿与图谱上下文，输出校验报告：
    - 缺失知识点 / 缺失考点 / 遗漏前置
    - 教学顺序是否符合拓扑序（按知识点在教案文本中的首次出现位置）
    """
    plan = state.get("lesson_plan") or {}
    plan_text = f"{plan.get('teaching_objectives', '')}\n{plan.get('teaching_process', '')}"

    missing_kps: list[str] = []
    missing_exam_points: list[str] = []
    missing_prereqs: list[str] = []

    for ctx in state["graph_context"]:
        name = ctx["name"]
        if name and name not in plan_text:
            missing_kps.append(name)
        for e in ctx.get("exam_points") or []:
            if e.get("name") and e.get("name") not in plan_text:
                missing_exam_points.append(f"{name}·{e['name']}（{e.get('level', '理解')}）")
        for pre in ctx.get("prerequisites") or []:
            if pre and pre not in plan_text:
                missing_prereqs.append(f"{name}←{pre}")

    # 教学顺序检查：按拓扑序比较知识点在教案中的首次出现位置
    order_issues: list[str] = []
    positions: list[tuple[int, str]] = []
    for ctx in state["graph_context"]:
        pos = plan_text.find(ctx["name"])
        if pos >= 0:
            positions.append((pos, ctx["name"]))
    positions.sort()
    seen_names = [n for _, n in positions]
    for ctx in state["graph_context"]:
        name = ctx["name"]
        if name not in seen_names:
            continue
        idx = seen_names.index(name)
        for pre in ctx.get("prerequisites") or []:
            if pre in seen_names and seen_names.index(pre) > idx:
                order_issues.append(f"「{name}」应在其前置「{pre}」之后讲解")

    report = {
        "missing_kps": missing_kps,
        "missing_exam_points": missing_exam_points,
        "missing_prereqs": missing_prereqs,
        "order_issues": order_issues,
        "passed": not (missing_kps or missing_exam_points or missing_prereqs or order_issues),
        "checked_count": len(state["graph_context"]),
    }
    return {"verification_report": report}


def build_lesson_plan_graph():
    """构建教案生成图（固定编排流水线，一键自动串行执行）。

    collect_context（图谱子图查询）→ retrieve_materials（RAG 教材检索）
    → generate（LLM 生成初稿）→ verify（规则校验）→ END
    """
    graph = StateGraph(LessonPlanState)
    graph.add_node("collect_context", _collect_context)
    graph.add_node("retrieve_materials", _retrieve_materials)
    graph.add_node("generate", _generate)
    graph.add_node("verify", _verify_plan)

    graph.add_edge(START, "collect_context")
    graph.add_edge("collect_context", "retrieve_materials")
    graph.add_edge("retrieve_materials", "generate")
    graph.add_edge("generate", "verify")
    graph.add_edge("verify", END)
    return graph.compile()


_lesson_plan_graph = None


def run_lesson_plan(
    *,
    owner_id: str,
    knowledge_point_ids: list[str],
    subject: str = "",
    grade_level: str = "",
    requirements: str = "",
    style: str = "",
    chapter: str = "",
) -> dict:
    """执行固定流水线备课图，返回 {"lesson_plan": {...}, "verification_report": {...}, "error": ""}"""
    global _lesson_plan_graph
    if _lesson_plan_graph is None:
        _lesson_plan_graph = build_lesson_plan_graph()
    state: LessonPlanState = {
        "owner_id": owner_id,
        "knowledge_point_ids": knowledge_point_ids,
        "subject": subject,
        "grade_level": grade_level,
        "requirements": requirements,
        "style": style,
        "chapter": chapter,
        "graph_context": [],
        "materials": [],
        "lesson_plan": {},
        "verification_report": {},
        "error": "",
    }
    result = _lesson_plan_graph.invoke(state)
    return {
        "lesson_plan": result.get("lesson_plan", {}),
        "graph_context": result.get("graph_context", []),
        "verification_report": result.get("verification_report", {}),
        "error": result.get("error", ""),
    }
