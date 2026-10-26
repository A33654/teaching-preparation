"""作业管理 API —— 覆盖三个功能性需求：

FR-01 从教案一键生成作业：取教案「课堂习题」为初始题目，自动继承教案关联知识点，
        教师可增删改。
FR-02 作业编辑与题型支持：选择/填空/简答/论述四类；每题必选 ≥1 关联知识点；
        填空答案支持多解；提交（发布）时未关联知识点的题被拦截。
FR-03 发布与（模拟）提交：发布后生成提交入口；本期学生提交以「模拟提交/教师代录」
        实现，不依赖学生端；提交后生成 Submission，状态=已提交，学号以哈希存储。
"""
import hashlib
import uuid

from fastapi import APIRouter, HTTPException
from sqlmodel import SQLModel, col, select

from app.api.deps import CurrentUser, SessionDep
from app.core import access, telemetry
from app.core.config import settings
from app.knowledge_graph import KnowledgeGraphRepository
from app.models import (
    Homework,
    HomeworkPublic,
    HomeworkQuestion,
    HomeworksPublic,
    HomeworkStatus,
    HomeworkUpdate,
    KnowledgePointOut,
    LessonPlan,
    QuestionType,
    SimulateSubmitRequest,
    Submission,
    SubmissionPublic,
    SubmissionsPublic,
    SubmissionStatus,
)

router = APIRouter(prefix="/homework", tags=["homework"])


class GenerateHomeworkRequest(SQLModel):
    """一键生成作业入参：title 可选，缺省用教案标题派生。"""
    title: str | None = None


# ==================== 工具函数 ====================

def _hash_student_id(student_id: str) -> str:
    """学号哈希存储：sha256(学号 + 服务端密钥)，确定性、不可逆。"""
    return hashlib.sha256(
        (student_id + settings.SECRET_KEY).encode("utf-8")
    ).hexdigest()


def _resolve_kps(ids: list[str]) -> list[KnowledgePointOut]:
    """按 ID 从 Neo4j 解析知识点元信息（用于前端选择器展示）。"""
    if not ids:
        return []
    try:
        kps = KnowledgeGraphRepository().get_many_knowledge_points(ids)
        return [KnowledgePointOut(**kp) for kp in kps]
    except Exception:
        return []


def _to_public(hw: Homework) -> HomeworkPublic:
    return HomeworkPublic(
        id=hw.id,
        title=hw.title,
        lesson_plan_id=hw.lesson_plan_id,
        owner_id=hw.owner_id,
        org_id=hw.org_id,
        status=hw.status,
        knowledge_point_ids=hw.knowledge_point_ids or [],
        questions=[HomeworkQuestion(**q) for q in (hw.questions or [])],
        created_at=hw.created_at,
        updated_at=hw.updated_at,
        knowledge_points=_resolve_kps(hw.knowledge_point_ids or []),
    )


def _get_owned_homework(session: SessionDep, user: CurrentUser, hw_id: uuid.UUID) -> Homework:
    hw = session.get(Homework, hw_id)
    if not hw:
        raise HTTPException(404, "作业不存在")
    if not user.is_superuser and hw.owner_id != user.id:
        raise HTTPException(403, "无权访问该作业")
    return hw


def _missing_standard_answer(q: dict) -> bool:
    """客观题是否缺少标准答案（PRD §7③ 发布拦截的依据）。

    选择题：需指定 correct_option；填空题：需至少一个 answers。
    简答 / 论述题由 AI + 教师终评判定，不强制参考答案。
    """
    qtype = q.get("type")
    if qtype == "choice":
        return q.get("correct_option") is None
    if qtype == "fill":
        return not (q.get("answers") or [])
    return False


def _all_kp_ids(hw: Homework) -> list[str]:
    """作业的全部关联知识点（题目级 ∪ 作业级），去重保序。"""
    ids: list[str] = []
    for q in hw.questions or []:
        d = q.model_dump() if hasattr(q, "model_dump") else dict(q)
        for kp in d.get("knowledge_point_ids") or []:
            if kp not in ids:
                ids.append(kp)
    for kp in hw.knowledge_point_ids or []:
        if kp not in ids:
            ids.append(kp)
    return ids


def _exercise_to_question(ex: dict, inherited_kp_ids: list[str]) -> dict:
    """将教案课堂习题转换为作业题目 dict，自动继承教案关联知识点。"""
    q = dict(ex)
    q.pop("knowledge_point_ids", None)  # 继承，不取习题自带
    qtype = q.get("type", "short")
    try:
        QuestionType(qtype)
    except ValueError:
        qtype = "short"
    q["type"] = qtype
    q["id"] = str(q.get("id") or uuid.uuid4())
    q["stem"] = q.get("stem", "")
    q["knowledge_point_ids"] = list(inherited_kp_ids)  # 自动继承
    q["options"] = q.get("options", []) or []
    q["correct_option"] = q.get("correct_option")
    q["answers"] = q.get("answers", []) or []
    q["reference_answer"] = q.get("reference_answer", "") or ""
    return q


# ==================== FR-01：从教案一键生成作业 ====================

@router.post("/generate-from/{lesson_plan_id}", response_model=HomeworkPublic)
def generate_homework_from_lesson_plan(
    lesson_plan_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: GenerateHomeworkRequest | None = None,
) -> HomeworkPublic:
    """取该教案「课堂习题」为初始题目，题目自动继承教案关联知识点。

    Given 教师打开某份已生成教案，When 点击"生成作业"，
    Then 进入作业编辑页且题目与知识点预填，可编辑。
    """
    lp = session.get(LessonPlan, lesson_plan_id)
    if not lp:
        raise HTTPException(404, "教案不存在")
    if not current_user.is_superuser and not access.can_view_lesson_plan(session, current_user, lp):
        raise HTTPException(403, "无权访问该教案")

    inherited_kp_ids = lp.knowledge_point_ids or []
    exercises = lp.classroom_exercises or []
    questions = [_exercise_to_question(ex, inherited_kp_ids) for ex in exercises]

    title = (body.title if body and body.title else f"{lp.title} - 作业")[:255]
    hw = Homework(
        title=title,
        lesson_plan_id=lp.id,
        org_id=lp.org_id,
        owner_id=current_user.id,
        status=HomeworkStatus.DRAFT,
        knowledge_point_ids=list(inherited_kp_ids),
        questions=questions,
    )
    session.add(hw)
    session.commit()
    session.refresh(hw)
    return _to_public(hw)


# ==================== 作业 CRUD（FR-02 编辑基础） ====================

@router.get("/", response_model=HomeworksPublic)
def list_homeworks(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> HomeworksPublic:
    """作业列表：教师仅见本人，超管见全部。"""
    if current_user.is_superuser:
        stmt = select(Homework)
    else:
        stmt = select(Homework).where(Homework.owner_id == current_user.id)
    total = len(session.exec(stmt).all())
    rows = session.exec(
        stmt.order_by(col(Homework.updated_at).desc()).offset(skip).limit(limit)
    ).all()
    return HomeworksPublic(data=[_to_public(h) for h in rows], count=total)


@router.get("/{homework_id}", response_model=HomeworkPublic)
def get_homework(
    homework_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> HomeworkPublic:
    return _to_public(_get_owned_homework(session, current_user, homework_id))


@router.put("/{homework_id}", response_model=HomeworkPublic)
def update_homework(
    homework_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: HomeworkUpdate | None = None,
) -> HomeworkPublic:
    """编辑作业（增删改题目、知识点题库）。草稿态可保存；发布态不允许改题。"""
    body = body or HomeworkUpdate()
    hw = _get_owned_homework(session, current_user, homework_id)
    if hw.status != HomeworkStatus.DRAFT:
        raise HTTPException(400, "仅草稿态作业可编辑，请先关闭作业再编辑")
    if body.title is not None:
        hw.title = body.title
    if body.knowledge_point_ids is not None:
        hw.knowledge_point_ids = body.knowledge_point_ids
    if body.questions is not None:
        # 规范化每题结构，保证后续发布校验可靠
        norm: list[dict] = []
        for q in body.questions:
            d = q.model_dump() if isinstance(q, HomeworkQuestion) else dict(q)
            d["id"] = str(d.get("id") or uuid.uuid4())
            d.setdefault("knowledge_point_ids", [])
            d.setdefault("options", [])
            d.setdefault("answers", [])
            norm.append(d)
        hw.questions = norm
    from datetime import datetime, timezone

    hw.updated_at = datetime.now(timezone.utc)
    session.add(hw)
    session.commit()
    session.refresh(hw)
    return _to_public(hw)


# ==================== FR-02：发布（含知识点校验拦截） ====================

@router.post("/{homework_id}/publish", response_model=HomeworkPublic)
def publish_homework(
    homework_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> HomeworkPublic:
    """发布作业：生成提交入口。

    提交（发布）时，未关联知识点的题目被拦截（FR-02 验收点）。
    """
    hw = _get_owned_homework(session, current_user, homework_id)
    if hw.status == HomeworkStatus.PUBLISHED:
        raise HTTPException(400, "作业已发布")
    if not hw.questions:
        raise HTTPException(400, "作业尚无题目，无法发布")

    # 校验：每题必须关联 ≥1 个知识点
    bad = [
        i + 1
        for i, q in enumerate(hw.questions)
        if not (q.get("knowledge_point_ids") if isinstance(q, dict) else q.knowledge_point_ids)
    ]
    if bad:
        raise HTTPException(
            422,
            f"第 {', '.join(map(str, bad))} 题未关联知识点，发布前每题必须选择至少 1 个知识点",
        )

    # 校验：客观题必须有标准答案（PRD §7③ —— 发布时拦截，而非判分侧兜底）
    missing = [
        i + 1
        for i, q in enumerate(hw.questions)
        if _missing_standard_answer(
            q.model_dump() if hasattr(q, "model_dump") else dict(q)
        )
    ]
    if missing:
        raise HTTPException(
            422,
            f"第 {', '.join(map(str, missing))} 题缺少标准答案"
            "（选择题需指定正确选项，填空题需填写答案），请补全标准答案后再发布",
        )

    hw.status = HomeworkStatus.PUBLISHED
    from datetime import datetime, timezone

    hw.updated_at = datetime.now(timezone.utc)
    session.add(hw)
    session.commit()
    session.refresh(hw)

    # PRD §5.3 埋点：assignment_published
    telemetry.emit(
        "assignment_published",
        homework_id=str(hw.id),
        question_count=len(hw.questions or []),
        knowledge_point_count=len(_all_kp_ids(hw)),
        user_id=str(current_user.id),
    )
    return _to_public(hw)


# ==================== FR-03：发布后（模拟）提交 ====================

@router.post("/{homework_id}/simulate-submit", response_model=SubmissionPublic)
def simulate_submit(
    homework_id: uuid.UUID,
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: SimulateSubmitRequest,
) -> SubmissionPublic:
    """模拟提交 / 教师代录：不依赖学生端。

    Given 作业已发布，When 教师用"模拟提交"录入一份答案，
    Then 生成 Submission 且状态=已提交，学号以哈希存储。
    """
    hw = _get_owned_homework(session, current_user, homework_id)
    if hw.status != HomeworkStatus.PUBLISHED:
        raise HTTPException(400, "仅已发布的作业可接受提交")
    if hw.status == HomeworkStatus.CLOSED:
        raise HTTPException(400, "该作业已截止，不再接受提交")

    student_hash = _hash_student_id(body.student_id)  # 学号哈希存储

    # PRD §7④：同一学生重复提交以最后一次为准 —— 旧提交标记「被覆盖」并保留留痕
    for old in session.exec(
        select(Submission).where(
            Submission.homework_id == hw.id,
            Submission.student_id_hash == student_hash,
            col(Submission.superseded).is_(False),
        )
    ).all():
        old.superseded = True
        session.add(old)

    sub = Submission(
        homework_id=hw.id,
        org_id=hw.org_id,
        student_id_hash=student_hash,
        answers=body.answers or [],
        status=SubmissionStatus.SUBMITTED,
        superseded=False,
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return SubmissionPublic(
        id=sub.id,
        homework_id=sub.homework_id,
        student_id_hash=sub.student_id_hash,
        answers=sub.answers,
        status=sub.status,
        superseded=sub.superseded,
        submitted_at=sub.submitted_at,
        created_at=sub.created_at,
    )


@router.get("/{homework_id}/submissions", response_model=SubmissionsPublic)
def list_submissions(
    homework_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> SubmissionsPublic:
    """查看某作业的全部提交（模拟提交产生的 Submission 列表）。"""
    _get_owned_homework(session, current_user, homework_id)
    subs = session.exec(
        select(Submission)
        .where(Submission.homework_id == homework_id)
        .order_by(col(Submission.submitted_at).desc())
    ).all()
    data = [
        SubmissionPublic(
            id=s.id,
            homework_id=s.homework_id,
            student_id_hash=s.student_id_hash,
            answers=s.answers,
            status=s.status,
            superseded=s.superseded,
            submitted_at=s.submitted_at,
            created_at=s.created_at,
        )
        for s in subs
    ]
    return SubmissionsPublic(data=data, count=len(data))


# ==================== PRD §4 / §9 R-3：作业截止 ====================


@router.post("/{homework_id}/close", response_model=HomeworkPublic)
def close_homework(
    homework_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> HomeworkPublic:
    """使作业进入「已截止」状态（手动截止入口）。

    截止后不再接受新的模拟提交；如需继续编辑，请新建作业。
    """
    from datetime import datetime, timezone

    hw = _get_owned_homework(session, current_user, homework_id)
    if hw.status == HomeworkStatus.CLOSED:
        raise HTTPException(400, "作业已截止")
    if hw.status == HomeworkStatus.DRAFT:
        raise HTTPException(400, "草稿态作业尚未发布，无需截止")

    hw.status = HomeworkStatus.CLOSED
    hw.updated_at = datetime.now(timezone.utc)
    session.add(hw)
    session.commit()
    session.refresh(hw)

    telemetry.emit(
        "assignment_closed",
        homework_id=str(hw.id),
        question_count=len(hw.questions or []),
        user_id=str(current_user.id),
    )
    return _to_public(hw)
