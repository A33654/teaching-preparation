"""FR-07/08/09 纯逻辑单元测试（不依赖数据库）。"""
from __future__ import annotations

import hashlib
import uuid

from app.core.config import settings
from app.grading.analytics import extract_wrong_expression, is_wrong
from app.grading.export_service import anonymous_identity, build_export_rows, write_pdf, write_xlsx
from app.models import Homework, HomeworkStatus, Submission, SubmissionGrade, SubmissionStatus

PLAIN_STUDENT_ID = "2026001"  # 明文学号，仅存在于入参；导出结果中不得出现


def _hash(sid: str) -> str:
    return hashlib.sha256((sid + settings.SECRET_KEY).encode("utf-8")).hexdigest()


def _fixture():
    hw_id = uuid.uuid4()
    hw = Homework(
        id=hw_id,
        title="脱敏导出验收作业",
        owner_id=uuid.uuid4(),
        status=HomeworkStatus.PUBLISHED,
        knowledge_point_ids=["kp-A"],
        questions=[
            {
                "id": "q0",
                "type": "choice",
                "stem": "光的三线辨析",
                "knowledge_point_ids": ["kp-A"],
                "options": ["直线传播", "折射", "反射", "散射"],
                "correct_option": 1,
                "answers": [],
                "reference_answer": "",
                "score": 5.0,
            },
            {
                "id": "q1",
                "type": "short",
                "stem": "简述光的折射",
                "knowledge_point_ids": ["kp-A"],
                "options": [],
                "correct_option": None,
                "answers": [],
                "reference_answer": "传播方向改变叫折射",
                "score": 10.0,
            },
        ],
    )
    sub = Submission(
        id=uuid.uuid4(),
        homework_id=hw_id,
        student_id_hash=_hash(PLAIN_STUDENT_ID),
        status=SubmissionStatus.GRADED,
        answers=[
            {"question_id": "q0", "content": 2},
            {"question_id": "q1", "content": "光会突然消失"},
        ],
    )
    grades = [
        SubmissionGrade(
            id=uuid.uuid4(),
            submission_id=sub.id,
            question_id="q0",
            question_type="choice",
            full_score=5.0,
            is_correct=False,
            auto_score=0.0,
            auto_detail="学生选 C，标准答案 B",
        ),
        SubmissionGrade(
            id=uuid.uuid4(),
            submission_id=sub.id,
            question_id="q1",
            question_type="short",
            full_score=10.0,
            ai_suggested_score=2.0,
            ai_comment="要点缺失较多",
            ai_confidence=0.55,
            needs_human=True,
        ),
    ]
    return hw, [sub], grades


def test_export_rows_contain_no_plaintext_identity():
    """FR-09：导出内容中不含明文学号，仅哈希标识与派生昵称。"""
    hw, subs, grades = _fixture()
    summary, detail = build_export_rows(hw, subs, grades)

    blob = str(summary) + str(detail)
    assert PLAIN_STUDENT_ID not in blob

    expect_hash = subs[0].student_id_hash
    assert expect_hash[:12] in blob  # 哈希标识存在（脱敏后身份仍可对齐）
    # 身份列只用哈希前缀，不暴露完整哈希以外的任何信息
    for row in summary:
        assert row[0] == expect_hash[:12]
        assert row[1].startswith("学生")


def test_anonymous_identity_is_hash_derived():
    digest = _hash(PLAIN_STUDENT_ID)
    ident, nick = anonymous_identity(digest)
    assert ident == digest[:12]
    assert nick == f"学生{digest[:4].upper()}"
    assert PLAIN_STUDENT_ID not in ident and PLAIN_STUDENT_ID not in nick


def test_export_rows_detail_structure():
    hw, subs, grades = _fixture()
    summary, detail = build_export_rows(hw, subs, grades)
    assert len(summary) == 1
    assert len(detail) == 2
    # 汇总：得分 = 0 + 2 = 2，满分 15
    assert summary[0][2] == 2.0
    assert summary[0][3] == 15.0
    # 明细含学生作答与判分结果
    assert "光会突然消失" in str(detail[1])
    assert "AI 建议" in detail[1][6]


def test_write_xlsx_file_has_no_plaintext(tmp_path):
    """FR-09：真实生成的 xlsx 文件（解压后）不含明文学号。"""
    import zipfile

    hw, subs, grades = _fixture()
    summary, detail = build_export_rows(hw, subs, grades)
    path = str(tmp_path / "export.xlsx")
    write_xlsx(path, hw.title, summary, detail)

    texts = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            texts.append(z.read(name).decode("utf-8", errors="ignore"))
    joined = "".join(texts)
    assert PLAIN_STUDENT_ID not in joined
    assert subs[0].student_id_hash[:12] in joined


def test_write_pdf_file_is_generated(tmp_path):
    """FR-09：PDF 可生成且非空（中文字体已注册，行数据来自同一脱敏构造）。"""
    hw, subs, grades = _fixture()
    summary, detail = build_export_rows(hw, subs, grades)
    path = str(tmp_path / "export.pdf")
    write_pdf(path, hw.title, summary, detail)
    with open(path, "rb") as f:
        head = f.read(8)
    assert head.startswith(b"%PDF-")
    assert __import__("os").path.getsize(path) > 1000


def test_extract_wrong_expression_choice_and_text():
    q = {"type": "choice", "options": ["甲", "乙", "丙", "丁"]}
    assert extract_wrong_expression(q, 2) == "误选 C（丙）"
    assert extract_wrong_expression(q, "C") == "误选 C（丙）"
    assert extract_wrong_expression(q, None) == "（未作答）"
    assert extract_wrong_expression({"type": "fill"}, "反射") == "反射"


def test_is_wrong_for_objective_and_subjective():
    g = SubmissionGrade(
        submission_id=uuid.uuid4(), question_id="q0", question_type="choice",
        full_score=5.0, is_correct=False,
    )
    assert is_wrong(g) is True

    # 主观题：得分率 2/10 = 0.2 < 0.6 → 计入错误
    g2 = SubmissionGrade(
        submission_id=uuid.uuid4(), question_id="q1", question_type="short",
        full_score=10.0, ai_suggested_score=2.0,
    )
    assert is_wrong(g2) is True

    # 主观题：得分率 9/10 = 0.9 ≥ 0.6 → 不计入错误
    g3 = SubmissionGrade(
        submission_id=uuid.uuid4(), question_id="q1", question_type="short",
        full_score=10.0, ai_suggested_score=9.0,
    )
    assert is_wrong(g3) is False

    # 终评覆盖 AI 建议：终评 0 分 → 计错
    g4 = SubmissionGrade(
        submission_id=uuid.uuid4(), question_id="q1", question_type="short",
        full_score=10.0, ai_suggested_score=9.0, final_score=0.0, finalized=True,
    )
    assert is_wrong(g4) is True
