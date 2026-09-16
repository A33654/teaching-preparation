"""文件概括 + PPT 生成 + PPT 列表 —— LLM 部分走 LangGraph 概括图/PPT大纲图"""
import io
import json
import os
import tempfile
import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import col, func, select

from app.agent.graphs import run_ppt_outline, run_summarize
from app.api.deps import CurrentUser, SessionDep
from app.models import PptRecord, PptRecordPublic, PptRecordsPublic

router = APIRouter(prefix="/summarize", tags=["summarize"])


class SummarizeResponse(BaseModel):
    summary: str
    key_topics: list[str]
    suggested_approach: str


async def _read_upload_text(file: UploadFile) -> str:
    """读取上传文件并解析文本"""
    content = await file.read()
    ext = (file.filename or "file").rsplit(".", 1)[-1] if file.filename else "txt"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        from app.file_parser import extract_text

        text = extract_text(tmp_path, ext if ext in ("pdf", "docx", "txt") else "txt")
    finally:
        os.unlink(tmp_path)
    if not text or len(text.strip()) < 10:
        raise HTTPException(400, "文件内容为空或无法解析")
    return text


@router.post("/", response_model=SummarizeResponse)
async def summarize_document(
    *, session: SessionDep, current_user: CurrentUser, file: UploadFile = File(...)
):
    """上传文件 → LangGraph 概括图生成概括"""
    text = await _read_upload_text(file)
    result = run_summarize(text)
    return SummarizeResponse(
        summary=result["summary"],
        key_topics=result["key_topics"],
        suggested_approach=result["suggested_approach"],
    )


# ==================== PPT 生成 ====================

# 风格主题：不同风格使用完全不同的配色与版式布局
STYLE_THEMES = {
    "professional": {
        "label": "专业",
        "accent": (0x1A, 0x56, 0xDB),   # 深蓝
        "accent_light": (0xE8, 0xF0, 0xFE),
        "text": (0x33, 0x33, 0x33),
        "layout": "bar",                 # 竖色条 + 分隔线
    },
    "vivid": {
        "label": "活泼",
        "accent": (0xFF, 0x6B, 0x35),    # 橙
        "accent_light": (0xFF, 0xF0, 0xE8),
        "text": (0x2D, 0x2D, 0x2D),
        "layout": "card",                # 色块封面 + 卡片式要点
    },
    "minimal": {
        "label": "简约",
        "accent": (0x22, 0x22, 0x22),    # 黑
        "accent_light": (0xF5, 0xF5, 0xF5),
        "text": (0x44, 0x44, 0x44),
        "layout": "line",                # 纯白 + 细线 + 大留白
    },
}


def _build_cover(prs, prs_title: str, theme: dict) -> None:
    """封面页：三种版式"""
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    from pptx.enum.shapes import MSO_SHAPE

    accent = theme["accent"]
    layout = theme["layout"]
    cover = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    if layout == "card":
        # 活泼：满幅橙黄色块 + 白色大标题 + 装饰圆点
        cover.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5)
        ).fill.solid()
        cover.shapes[-1].fill.fore_color.rgb = RGBColor(*accent)
        cover.shapes[-1].line.fill.background()
        box = cover.shapes.add_textbox(Inches(1.2), Inches(2.6), Inches(11), Inches(2.4))
        box.text_frame.text = prs_title
        box.text_frame.paragraphs[0].font.size = Pt(48)
        box.text_frame.paragraphs[0].font.bold = True
        box.text_frame.paragraphs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        # 装饰圆点
        for cx, color in ((Inches(1.6), (0xFF, 0xD9, 0x3D)), (Inches(2.4), (0xFF, 0xFF, 0xFF)), (Inches(3.2), (0xFF, 0xD9, 0x3D))):
            dot = cover.shapes.add_shape(MSO_SHAPE.OVAL, cx, Inches(1.6), Inches(0.45), Inches(0.45))
            dot.fill.solid()
            dot.fill.fore_color.rgb = RGBColor(*color)
            dot.line.fill.background()
    elif layout == "line":
        # 简约：白底 + 黑字标题 + 一条细线
        box = cover.shapes.add_textbox(Inches(1.2), Inches(3.0), Inches(11), Inches(1.5))
        box.text_frame.text = prs_title
        box.text_frame.paragraphs[0].font.size = Pt(40)
        box.text_frame.paragraphs[0].font.bold = True
        box.text_frame.paragraphs[0].font.color.rgb = RGBColor(*accent)
        line = cover.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(4.6), Inches(1.6), Inches(0.04))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(*accent)
        line.line.fill.background()
    else:
        # 专业：左侧竖色条 + 标题
        bar = cover.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.28), Inches(7.5))
        bar.fill.solid()
        bar.fill.fore_color.rgb = RGBColor(*accent)
        bar.line.fill.background()
        box = cover.shapes.add_textbox(Inches(1.0), Inches(2.7), Inches(11), Inches(2))
        box.text_frame.text = prs_title
        box.text_frame.paragraphs[0].font.size = Pt(44)
        box.text_frame.paragraphs[0].font.bold = True
        box.text_frame.paragraphs[0].font.color.rgb = RGBColor(*accent)
        sub = cover.shapes.add_textbox(Inches(1.0), Inches(4.6), Inches(8), Inches(0.5))
        sub.text_frame.text = "AI 智能备课 · 教学课件"
        sub.text_frame.paragraphs[0].font.size = Pt(16)
        sub.text_frame.paragraphs[0].font.color.rgb = RGBColor(0x99, 0x99, 0x99)


def _build_content_slide(prs, slide_data: dict, theme: dict) -> None:
    """内容页：三种版式"""
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN

    accent = theme["accent"]
    accent_light = theme["accent_light"]
    text_color = theme["text"]
    layout = theme["layout"]

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bullets = slide_data.get("bullets", [])
    title = slide_data.get("title", "")

    if layout == "card":
        # 活泼：顶部色条 + 标题 + 圆角卡片式要点（浅橙底）
        top = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.16))
        top.fill.solid()
        top.fill.fore_color.rgb = RGBColor(*accent)
        top.line.fill.background()
        title_box = slide.shapes.add_textbox(Inches(0.9), Inches(0.5), Inches(11.5), Inches(1))
        title_box.text_frame.text = title
        title_box.text_frame.paragraphs[0].font.size = Pt(30)
        title_box.text_frame.paragraphs[0].font.bold = True
        title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(*accent)
        # 卡片式要点
        card_h = Inches(0.78)
        gap = Inches(0.16)
        for i, bullet in enumerate(bullets[:5]):
            top_pos = Inches(1.7) + i * (card_h + gap)
            card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.2), top_pos, Inches(10.9), card_h
            )
            card.fill.solid()
            card.fill.fore_color.rgb = RGBColor(*accent_light)
            card.line.color.rgb = RGBColor(*accent)
            card.line.width = Pt(1)
            tf = card.text_frame
            tf.text = bullet
            tf.paragraphs[0].font.size = Pt(18)
            tf.paragraphs[0].font.bold = True
            tf.paragraphs[0].font.color.rgb = RGBColor(*text_color)
            tf.margin_left = Inches(0.3)
            tf.margin_top = Inches(0.12)
    elif layout == "line":
        # 简约：黑标题 + 细线 + 大留白要点（无圆点）
        title_box = slide.shapes.add_textbox(Inches(1.2), Inches(0.7), Inches(11), Inches(1))
        title_box.text_frame.text = title
        title_box.text_frame.paragraphs[0].font.size = Pt(28)
        title_box.text_frame.paragraphs[0].font.bold = True
        title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(*accent)
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.6), Inches(0.9), Inches(0.035))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(*accent)
        line.line.fill.background()
        box = slide.shapes.add_textbox(Inches(1.2), Inches(2.1), Inches(10.9), Inches(4.6))
        tf = box.text_frame
        for i, bullet in enumerate(bullets[:6]):
            if i == 0:
                tf.paragraphs[0].text = bullet
                tf.paragraphs[0].font.size = Pt(18)
            else:
                p = tf.add_paragraph()
                p.text = bullet
                p.font.size = Pt(18)
                p.space_before = Pt(14)
            tf.paragraphs[i].font.color.rgb = RGBColor(*text_color)
    else:
        # 专业：标题 + 色条分隔线 + 圆点要点
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(1))
        title_box.text_frame.text = title
        title_box.text_frame.paragraphs[0].font.size = Pt(32)
        title_box.text_frame.paragraphs[0].font.bold = True
        title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(*accent)
        sep = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.3), Inches(11.7), Inches(0.03))
        sep.fill.solid()
        sep.fill.fore_color.rgb = RGBColor(*accent)
        sep.line.fill.background()
        box = slide.shapes.add_textbox(Inches(1.2), Inches(1.6), Inches(10.9), Inches(5))
        tf = box.text_frame
        for i, bullet in enumerate(bullets[:6]):
            if i == 0:
                tf.paragraphs[0].text = f"• {bullet}"
                tf.paragraphs[0].font.size = Pt(20)
            else:
                p = tf.add_paragraph()
                p.text = f"• {bullet}"
                p.font.size = Pt(20)
            tf.paragraphs[i].font.color.rgb = RGBColor(*text_color)


def _build_pptx(prs_title: str, slides_data: list[dict], style: str = "professional") -> io.BytesIO:
    """按风格主题渲染幻灯片（不同风格 = 不同配色 + 不同版式）"""
    from pptx import Presentation
    from pptx.util import Inches

    theme = STYLE_THEMES.get(style, STYLE_THEMES["professional"])

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    _build_cover(prs, prs_title, theme)
    for slide_data in slides_data:
        _build_content_slide(prs, slide_data, theme)

    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer


@router.post("/generate-ppt")
async def generate_ppt(
    *, session: SessionDep, current_user: CurrentUser, file: UploadFile = File(...),
    style: str = Form(default="professional"), slide_count: int = Form(default=8),
):
    """上传文件 → LangGraph PPT 大纲图生成内容 → 渲染 PPTX 文件"""
    text = await _read_upload_text(file)

    # LangGraph PPT 大纲图
    slides_data = run_ppt_outline(text, style=style, slide_count=slide_count)

    safe_name = (file.filename or "presentation").rsplit(".", 1)[0][:30]
    buffer = _build_pptx(safe_name, slides_data, style=style)

    # 保存 PPT 记录
    ppt_path = f"uploads/ppt/{uuid.uuid4()}.pptx"
    os.makedirs("uploads/ppt", exist_ok=True)
    with open(ppt_path, "wb") as f:
        f.write(buffer.getvalue())
    buffer.seek(0)

    record = PptRecord(
        title=safe_name,
        original_filename=file.filename or "presentation",
        file_path=ppt_path,
        file_size=len(buffer.getvalue()),
        slide_count=len(slides_data),
        extracted_text=text[:5000] if text else "",
        slides_json=json.dumps(slides_data, ensure_ascii=False),
        style=style,
        owner_id=current_user.id,
    )
    session.add(record)
    session.commit()

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}.pptx"},
    )


# ==================== PPT 列表 & 导出 ====================


@router.get("/ppt-list", response_model=PptRecordsPublic)
def list_ppts(session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100):
    if current_user.is_superuser:
        cs = select(func.count()).select_from(PptRecord)
        st = select(PptRecord)
    else:
        cs = select(func.count()).select_from(PptRecord).where(PptRecord.owner_id == current_user.id)
        st = select(PptRecord).where(PptRecord.owner_id == current_user.id)
    count = session.exec(cs).one()
    st = st.order_by(col(PptRecord.created_at).desc()).offset(skip).limit(limit)
    records = session.exec(st).all()
    return PptRecordsPublic(
        data=[PptRecordPublic.model_validate(r) for r in records],
        count=count,
    )


class SavePptRequest(BaseModel):
    slides: list[dict]
    style: str = "professional"


@router.put("/ppt/{ppt_id}/save")
def save_ppt(ppt_id: str, *, session: SessionDep, current_user: CurrentUser, body: SavePptRequest):
    """保存编辑后的 PPT 幻灯片并重新生成 PPTX"""
    try:
        uid = uuid.UUID(ppt_id)
    except ValueError:
        raise HTTPException(400, "无效ID")
    rec = session.get(PptRecord, uid)
    if not rec:
        raise HTTPException(404, "PPT不存在")
    if not current_user.is_superuser and rec.owner_id != current_user.id:
        raise HTTPException(403, "无权访问")

    rec.slides_json = json.dumps(body.slides, ensure_ascii=False)
    rec.style = body.style
    rec.slide_count = len(body.slides)
    session.add(rec)
    session.commit()

    buf = _build_pptx(rec.title, body.slides, accent=(0xE8, 0x91, 0xB0))
    with open(rec.file_path, "wb") as f:
        f.write(buf.getvalue())
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(rec.title)}.pptx"},
    )


@router.get("/ppt/{ppt_id}/export")
def export_ppt(ppt_id: str, session: SessionDep, current_user: CurrentUser):
    try:
        uid = uuid.UUID(ppt_id)
    except ValueError:
        raise HTTPException(400, "无效ID")
    rec = session.get(PptRecord, uid)
    if not rec:
        raise HTTPException(404, "PPT不存在")
    if not current_user.is_superuser and rec.owner_id != current_user.id:
        raise HTTPException(403, "无权访问")
    if not os.path.exists(rec.file_path):
        raise HTTPException(404, "文件已删除")
    with open(rec.file_path, "rb") as f:
        data = f.read()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(rec.title)}.pptx"},
    )
