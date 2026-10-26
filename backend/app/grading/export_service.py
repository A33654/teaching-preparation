"""FR-09 脱敏导出：按班级/个人导出成绩与批改明细（Excel / PDF）。

脱敏策略：
- 学生身份一律以「学号哈希前缀 + 由哈希派生的匿名昵称」呈现
- 数据库本身不存明文学号/姓名（入库即 sha256 哈希），导出链路也不可能触及明文
- 汇总与明细两级输出分别对应「成绩」与「批改明细」
"""
from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape

import xlsxwriter  # type: ignore[import-untyped]
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4, landscape  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.grading.service import question_dicts

CJK_FONT = "STSong-Light"

SUMMARY_HEADERS = ["学生标识（哈希）", "匿名昵称", "得分", "满分", "得分率"]
DETAIL_HEADERS = [
    "学生标识（哈希）",
    "匿名昵称",
    "题号",
    "题型",
    "题目",
    "学生作答",
    "判分结果",
    "自动/建议分",
    "终评分",
    "评语",
    "关联知识点",
]

TYPE_TEXT = {"choice": "选择", "fill": "填空", "short": "简答", "essay": "论述"}


def _register_cjk_font() -> None:
    """注册 reportlab 内置中文 CID 字体（无需外部字体文件）。"""
    try:
        pdfmetrics.getFont(CJK_FONT)
    except Exception:
        pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))


def anonymous_identity(student_id_hash: str, index: int = 0) -> tuple[str, str]:
    """脱敏身份：返回 (哈希标识, 匿名昵称)。二者均由哈希派生，不含明文。"""
    digest = (student_id_hash or "").strip()
    if not digest:
        return f"未知-{index + 1}", f"匿名-{index + 1}"
    return digest[:12], f"学生{digest[:4].upper()}"


def effective_score(g) -> float:
    """该题的有效得分：终评分 > 自动判分 > AI 建议分。"""
    if g.final_score is not None:
        return float(g.final_score)
    if g.auto_score is not None:
        return float(g.auto_score)
    return float(g.ai_suggested_score or 0.0)


def _result_text(g) -> str:
    if g.question_type in ("choice", "fill"):
        if g.is_correct is None:
            return "未判分"
        return "正确" if g.is_correct else "错误"
    if g.final_score is not None:
        return f"终评 {g.final_score} 分"
    conf = g.ai_confidence
    return f"AI 建议 {g.ai_suggested_score} 分" + (
        f"（置信度 {conf:.2f}）" if conf is not None else ""
    )


def build_export_rows(homework, submissions: list, grades: list) -> tuple[list[list], list[list]]:
    """构造脱敏导出行：(成绩汇总行, 批改明细行)。两级行均不含明文身份。"""
    questions = question_dicts(homework)
    qmap = {str(q.get("id")): q for q in questions}
    order = {str(q.get("id")): i + 1 for i, q in enumerate(questions)}
    total_full = sum(float(q.get("score") or 0.0) for q in questions)

    by_sub: dict = {}
    for g in grades:
        by_sub.setdefault(str(g.submission_id), []).append(g)

    summary: list[list] = []
    detail: list[list] = []
    for idx, sub in enumerate(submissions):
        ident, nick = anonymous_identity(sub.student_id_hash, idx)
        rows = sorted(
            by_sub.get(str(sub.id), []), key=lambda g: order.get(g.question_id, 999)
        )
        earned = sum(effective_score(g) for g in rows)
        rate = f"{(earned / total_full * 100):.1f}%" if total_full else "—"
        summary.append([ident, nick, round(earned, 1), round(total_full, 1), rate])

        # 该学生的题号 → 作答原文（仅作答内容，脱敏：不含任何身份信息）
        answers = {
            str(a.get("question_id")): str(a.get("content") or "")
            for a in sub.answers or []
        }

        for g in rows:
            q = qmap.get(g.question_id, {})
            kps = ", ".join(q.get("knowledge_point_ids") or [])
            detail.append(
                [
                    ident,
                    nick,
                    order.get(g.question_id, ""),
                    TYPE_TEXT.get(g.question_type, g.question_type),
                    str(q.get("stem") or "")[:80],
                    answers.get(g.question_id, "")[:120],
                    _result_text(g),
                    round(effective_score(g), 1),
                    "" if g.final_score is None else round(float(g.final_score), 1),
                    (g.final_comment or g.ai_comment or "")[:80],
                    kps,
                ]
            )

    return summary, detail


def write_xlsx(path: str, homework_title: str, summary: list[list], detail: list[list]) -> None:
    """导出 Excel：两个工作表——成绩汇总 / 批改明细。"""
    book = xlsxwriter.Workbook(path)
    head = book.add_format(
        {"bold": True, "bg_color": "#EEF3FA", "border": 1, "align": "center", "valign": "vcenter"}
    )
    cell = book.add_format({"border": 1, "valign": "top", "text_wrap": True})

    for sheet_name, headers, rows in (
        ("成绩汇总", SUMMARY_HEADERS, summary),
        ("批改明细", DETAIL_HEADERS, detail),
    ):
        ws = book.add_worksheet(sheet_name)
        for c, h in enumerate(headers):
            ws.write(0, c, h, head)
        for r, row in enumerate(rows, start=1):
            for c, v in enumerate(row):
                ws.write(r, c, v, cell)
        widths = [18, 12, 10, 10, 10] if sheet_name == "成绩汇总" else [18, 12, 6, 8, 30, 24, 16, 12, 10, 24, 18]
        for c, w in enumerate(widths):
            ws.set_column(c, c, w)
        ws.freeze_panes(1, 0)
    book.close()


def write_pdf(path: str, homework_title: str, summary: list[list], detail: list[list]) -> None:
    """导出 PDF：中文字体（STSong-Light），含成绩汇总与批改明细两张表。"""
    _register_cjk_font()
    doc = SimpleDocTemplate(
        path,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=12 * mm,
    )
    styles = ParagraphStyle("cjk", fontName=CJK_FONT, fontSize=8, leading=11)
    title_style = ParagraphStyle("t", fontName=CJK_FONT, fontSize=15, leading=20)

    def table_for(headers: list[str], rows: list[list], widths: list[float]) -> Table:
        data = [[Paragraph(xml_escape(str(h)), styles) for h in headers]]
        data += [[Paragraph(xml_escape("" if v is None else str(v)), styles) for v in r] for r in rows]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF3FA")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA5B1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ]
            )
        )
        return t

    story = [
        Paragraph(xml_escape(f"作业成绩与批改明细 · {homework_title}"), title_style),
        Paragraph(
            "说明：学生身份已脱敏，仅呈现学号哈希与派生匿名昵称，不含任何明文姓名/学号。",
            styles,
        ),
        Spacer(1, 8),
        Paragraph("一、成绩汇总", styles),
        Spacer(1, 4),
        table_for(SUMMARY_HEADERS, summary, [60, 50, 40, 40, 45]),
        Spacer(1, 12),
        Paragraph("二、批改明细", styles),
        Spacer(1, 4),
        table_for(DETAIL_HEADERS, detail, [60, 45, 22, 26, 90, 70, 55, 40, 32, 70, 55]),
    ]
    doc.build(story)
