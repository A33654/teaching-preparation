import enum
import uuid
from datetime import datetime, timezone

from pydantic import EmailStr
from sqlalchemy import DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# ==================== 枚举定义 ====================

class GradeLevel(str, enum.Enum):
    PRIMARY = "小学"
    JUNIOR = "初中"
    SENIOR = "高中"


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


# ==================== 用户 ====================

# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    nickname: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=20)
    avatar_url: str | None = Field(default=None, max_length=500)
    subject: str | None = Field(default=None, max_length=200)
    grade_level: str | None = Field(default=None, max_length=100)
    school: str | None = Field(default=None, max_length=200)
    subject: str | None = Field(default=None, max_length=200)
    grade_level: str | None = Field(default=None, max_length=100)
    school: str | None = Field(default=None, max_length=200)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)
    nickname: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=20)
    avatar_url: str | None = Field(default=None, max_length=500)
    subject: str | None = Field(default=None, max_length=200)
    grade_level: str | None = Field(default=None, max_length=100)
    school: str | None = Field(default=None, max_length=200)
    subject: str | None = Field(default=None, max_length=200)
    grade_level: str | None = Field(default=None, max_length=100)
    school: str | None = Field(default=None, max_length=200)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)
    lesson_plans: list["LessonPlan"] = Relationship(back_populates="owner", cascade_delete=True)
    documents: list["Document"] = Relationship(back_populates="owner", cascade_delete=True)
    ppt_records: list["PptRecord"] = Relationship(back_populates="owner", cascade_delete=True)
    schedules: list["Schedule"] = Relationship(back_populates="owner", cascade_delete=True)
    tasks: list["Task"] = Relationship(back_populates="owner", cascade_delete=True)
    subjects: list["Subject"] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore[assignment]


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)

  # ==================== 知识点（Neo4j 知识图谱节点，非 SQL 表） ====================

# 知识点与关系存储在 Neo4j 中（app/knowledge_graph/），
# 以下仅为 API 层的 Pydantic Schema。

class KnowledgePointCreate(SQLModel):
      """创建知识点请求体"""
      name: str = Field(min_length=1, max_length=255, description="知识点名称")
      description: str | None = Field(default=None, max_length=2000, description="描述")
      subject: str = Field(default="通用", min_length=1, max_length=100, description="学科")
      grade_level: GradeLevel | None = Field(default=None, description="学段")
      difficulty: int = Field(default=1, ge=1, le=5, description="难度 1-5")
      is_key_point: bool = Field(default=False, description="是否核心考点")


class KnowledgePointUpdate(SQLModel):
      """更新知识点请求体"""
      name: str | None = Field(default=None, min_length=1, max_length=255)
      description: str | None = Field(default=None, max_length=2000)
      subject: str | None = Field(default=None, min_length=1, max_length=100)
      grade_level: GradeLevel | None = None
      difficulty: int | None = Field(default=None, ge=1, le=5)
      is_key_point: bool | None = None


class KnowledgePointOut(SQLModel):
      """知识点返回体（数据来自 Neo4j）"""
      id: str
      name: str
      subject: str = "通用"
      description: str | None = None
      grade_level: str | None = None
      difficulty: int = 1
      is_key_point: bool = False
      owner_id: str | None = None
      created_at: str | None = None


class KnowledgePointsPublic(SQLModel):
      """知识点列表返回体"""
      data: list[KnowledgePointOut]
      count: int


class KnowledgeRelationCreate(SQLModel):
      """创建关系请求体"""
      target_id: str
      relation_type: str = "related_to"  # prerequisite | contains | related_to


class KnowledgeRelationOut(SQLModel):
      """关系返回体"""
      source_id: str
      target_id: str
      relation_type: str


  # ==================== 教案 ====================

class LessonPlanBase(SQLModel):
      """教案基础字段"""
      title: str = Field(min_length=1, max_length=255, description="教案标题")
      subject: str = Field(min_length=1, max_length=100, description="学科")
      grade_level: GradeLevel | None = Field(default=None, description="学段")
      teaching_objectives: str | None = Field(default=None, description="教学目标")
      teaching_process: str | None = Field(default=None, description="教学过程")


class LessonPlan(LessonPlanBase, table=True):
      """教案数据库表（知识点存于 Neo4j，这里仅存 ID 引用）"""
      id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
      created_at: datetime | None = Field(
          default_factory=get_datetime_utc,
          sa_type=DateTime(timezone=True),
      )
      owner_id: uuid.UUID = Field(
          foreign_key="user.id", nullable=False, ondelete="CASCADE"
      )
      owner: User | None = Relationship(back_populates="lesson_plans")
      subject_id: uuid.UUID | None = Field(default=None, foreign_key="subject.id", ondelete="SET NULL")
      extracted_text: str | None = Field(default=None)
      style: str | None = Field(default=None, max_length=50)
      # 关联的知识点 ID 列表（指向 Neo4j KnowledgePoint 节点）
      knowledge_point_ids: list[str] = Field(default_factory=list, sa_type=JSON)
      # 教案校验报告（固定流水线 verify 节点输出）
      verification_report: dict | None = Field(default=None, sa_type=JSON)


class LessonPlanCreate(SQLModel):
      """创建教案请求体"""
      title: str = Field(min_length=1, max_length=255)
      subject: str = Field(min_length=1, max_length=100)
      grade_level: GradeLevel | None = None
      teaching_objectives: str | None = None
      teaching_process: str | None = None
      knowledge_point_ids: list[str] = []
      subject_id: str | None = None


class LessonPlanUpdate(SQLModel):
      """更新教案请求体"""
      title: str | None = Field(default=None, min_length=1, max_length=255)
      subject: str | None = Field(default=None, min_length=1, max_length=100)
      grade_level: GradeLevel | None = None
      teaching_objectives: str | None = None
      teaching_process: str | None = None
      knowledge_point_ids: list[str] | None = None


class LessonPlanPublic(LessonPlanBase):
      """教案返回体（knowledge_points 从 Neo4j 按 ID 拉取）"""
      id: uuid.UUID
      owner_id: uuid.UUID
      subject_id: str | None = None
      created_at: datetime | None = None
      knowledge_point_ids: list[str] = []
      knowledge_points: list[KnowledgePointOut] = []


class LessonPlansPublic(SQLModel):
      """教案列表返回体"""
      data: list[LessonPlanPublic]
      count: int


# ==================== 文件上传与文档解析 ====================


class Document(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    filename: str = Field(max_length=500)
    original_filename: str = Field(max_length=500)
    file_type: str = Field(max_length=50)
    file_size: int = Field(default=0)
    file_path: str = Field(max_length=1000)
    status: DocumentStatus = Field(default=DocumentStatus.UPLOADED)
    error_message: str | None = Field(default=None, max_length=2000)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    owner: User | None = Relationship(back_populates="documents")
    extracted_text: str | None = Field(default=None)
    summary: str | None = Field(default=None)
    subject_id: uuid.UUID | None = Field(default=None, foreign_key="subject.id", ondelete="SET NULL")
    # 关联的知识点 ID 列表（指向 Neo4j KnowledgePoint 节点）
    knowledge_point_ids: list[str] = Field(default_factory=list, sa_type=JSON)


class DocumentPublic(SQLModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    status: DocumentStatus
    error_message: str | None = None
    created_at: datetime | None = None
    owner_id: uuid.UUID
    extracted_text: str | None = None
    summary: str | None = None
    subject_id: str | None = None
    knowledge_point_ids: list[str] = []
    knowledge_points: list[KnowledgePointOut] = []


class DocumentsPublic(SQLModel):
    data: list[DocumentPublic]
    count: int
# ==================== PPT 记录 ====================

class PptRecord(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=500)
    original_filename: str = Field(max_length=500)
    file_path: str = Field(max_length=1000)
    file_size: int = Field(default=0)
    slide_count: int = Field(default=0)
    extracted_text: str | None = Field(default=None)
    slides_json: str | None = Field(default=None)
    style: str | None = Field(default=None, max_length=50)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    owner: User | None = Relationship(back_populates="ppt_records")
    subject_id: uuid.UUID | None = Field(default=None, foreign_key="subject.id", ondelete="SET NULL")


class PptRecordPublic(SQLModel):
    id: uuid.UUID
    title: str
    subject_id: str | None = None
    original_filename: str
    file_size: int
    slide_count: int
    extracted_text: str | None = None
    slides_json: str | None = None
    style: str | None = None
    extracted_text: str | None = None
    slides_json: str | None = None
    style: str | None = None
    created_at: datetime | None = None
    owner_id: uuid.UUID


class PptRecordsPublic(SQLModel):
    data: list[PptRecordPublic]
    count: int

# ==================== 课程表 ====================

class Schedule(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    day_of_week: int = Field(ge=0, le=6)  # 0=周一, 6=周日
    start_time: str = Field(max_length=5)  # HH:MM
    end_time: str = Field(max_length=5)
    subject: str = Field(max_length=200)
    classroom: str = Field(default="", max_length=200)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    owner: User | None = Relationship(back_populates="schedules")

class ScheduleCreate(SQLModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str
    end_time: str
    subject: str
    classroom: str = ""

class SchedulePublic(SQLModel):
    id: uuid.UUID
    day_of_week: int
    start_time: str
    end_time: str
    subject: str
    classroom: str
    created_at: datetime | None = None
    owner_id: uuid.UUID

class SchedulesPublic(SQLModel):
    data: list[SchedulePublic]
    count: int


# ==================== 学习任务 ====================

class Task(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=500)
    description: str = Field(default="", max_length=2000)
    due_date: str = Field(default="", max_length=10)  # YYYY-MM-DD
    priority: str = Field(default="normal")  # high/normal/low
    completed: bool = Field(default=False)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    owner: User | None = Relationship(back_populates="tasks")

class TaskCreate(SQLModel):
    title: str
    description: str = ""
    due_date: str = ""
    priority: str = "normal"

class TaskPublic(SQLModel):
    id: uuid.UUID
    title: str
    description: str
    due_date: str
    priority: str
    completed: bool
    created_at: datetime | None = None
    owner_id: uuid.UUID

class TasksPublic(SQLModel):
    data: list[TaskPublic]
    count: int

# ==================== 学科 ====================

class Subject(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=200, unique=True)
    description: str | None = Field(default=None, max_length=500)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    owner: User | None = Relationship(back_populates="subjects")

class SubjectCreate(SQLModel):
    name: str
    description: str | None = None

class SubjectPublic(SQLModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    created_at: datetime | None = None
    owner_id: uuid.UUID

class SubjectsPublic(SQLModel):
    data: list[SubjectPublic]
    count: int


# ==================== 教材 ====================

class Textbook(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=500)
    version: str | None = Field(default=None, max_length=200)
    grade_level: str | None = Field(default=None, max_length=100)
    cover_url: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=1000)
    subject_id: uuid.UUID = Field(foreign_key="subject.id", nullable=False, ondelete="CASCADE")
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")

class TextbookCreate(SQLModel):
    name: str
    version: str | None = None
    grade_level: str | None = None
    cover_url: str | None = None
    description: str | None = None
    subject_id: str

class TextbookPublic(SQLModel):
    id: uuid.UUID
    name: str
    version: str | None = None
    grade_level: str | None = None
    cover_url: str | None = None
    description: str | None = None
    subject_id: uuid.UUID
    created_at: datetime | None = None
    owner_id: uuid.UUID

class TextbooksPublic(SQLModel):
    data: list[TextbookPublic]
    count: int


# ==================== 章节（树形结构） ====================

class Chapter(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=500)
    order_index: int = Field(default=0)
    level: int = Field(default=0)  # 0=教材, 1=单元, 2=小节
    parent_id: uuid.UUID | None = Field(default=None, foreign_key="chapter.id", ondelete="CASCADE")
    textbook_id: uuid.UUID = Field(foreign_key="textbook.id", nullable=False, ondelete="CASCADE")
    # 指向 Neo4j KnowledgePoint 节点 ID（无外键约束）
    knowledge_point_id: uuid.UUID | None = Field(default=None)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")

class ChapterCreate(SQLModel):
    title: str
    parent_id: str | None = None
    textbook_id: str
    level: int = 1

class ChapterPublic(SQLModel):
    id: uuid.UUID
    title: str
    order_index: int
    level: int
    parent_id: str | None = None
    textbook_id: uuid.UUID
    knowledge_point_id: str | None = None
    created_at: datetime | None = None
    children: list["ChapterPublic"] = []

class ChaptersPublic(SQLModel):
    data: list[ChapterPublic]
    count: int


# ==================== 候选知识点（待审核队列） ====================

class CandidateKnowledgePoint(SQLModel, table=True):
    """LLM 抽取 / 教师提交的候选知识点，管理员审核通过后才写入 Neo4j 图谱"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, index=True)
    subject: str = Field(default="通用", max_length=100)
    grade_level: str | None = Field(default=None, max_length=50)
    textbook_version: str | None = Field(default=None, max_length=200)
    definition: str | None = Field(default=None, max_length=2000)
    prerequisites: str | None = Field(default=None, max_length=1000)
    source: str = Field(default="llm_extraction", max_length=50)  # llm_extraction | teacher_submit
    status: str = Field(default="pending", max_length=20, index=True)  # pending | approved | rejected
    document_id: uuid.UUID | None = Field(default=None, index=True)
    submitter_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE")
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
    # 图谱共建工单类型：
    #   llm_extraction        文档批量抽取的候选知识点
    #   teacher_missing_kp    教师提交缺失知识点
    #   teacher_correction    教师对既有知识点提出纠错建议
    #   teacher_misconception 教师补充学生常见误区
    #   teacher_exam_point    教师补充考点
    #   auto_optimization     系统检测到章节覆盖不足自动生成的待优化工单
    kind: str | None = Field(default=None, max_length=50, index=True)
    target_kp_id: str | None = Field(default=None, max_length=64)  # 纠错/误区/考点指向的既有知识点
    suggestion: str | None = Field(default=None, max_length=2000)  # 纠错建议/补充说明


class CandidateCreate(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    subject: str = Field(default="通用", max_length=100)
    grade_level: str | None = Field(default=None, max_length=50)
    textbook_version: str | None = Field(default=None, max_length=200)
    definition: str | None = Field(default=None, max_length=2000)
    prerequisites: str | None = Field(default=None, max_length=1000)
    kind: str | None = Field(default=None, max_length=50)
    target_kp_id: str | None = Field(default=None, max_length=64)
    suggestion: str | None = Field(default=None, max_length=2000)


class CandidateUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=100)
    grade_level: str | None = Field(default=None, max_length=50)
    textbook_version: str | None = Field(default=None, max_length=200)
    definition: str | None = Field(default=None, max_length=2000)
    prerequisites: str | None = Field(default=None, max_length=1000)
    suggestion: str | None = Field(default=None, max_length=2000)


class CandidatePublic(SQLModel):
    id: uuid.UUID
    name: str
    subject: str
    grade_level: str | None = None
    textbook_version: str | None = None
    definition: str | None = None
    prerequisites: str | None = None
    source: str
    status: str
    document_id: uuid.UUID | None = None
    submitter_id: uuid.UUID
    created_at: datetime | None = None
    kind: str | None = None
    target_kp_id: str | None = None
    suggestion: str | None = None


class CandidatesPublic(SQLModel):
    data: list[CandidatePublic]
    count: int


# ==================== 系统任务日志 ====================

class ExtractionLog(SQLModel, table=True):
    """文档抽取 / 知识库更新等后台任务的运行日志（系统日志页数据源）"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    task_type: str = Field(max_length=50, index=True)  # document_upload | textbook_import | candidate_review
    status: str = Field(max_length=20)  # success | failed | info
    message: str = Field(max_length=2000)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


class ExtractionLogPublic(SQLModel):
    id: uuid.UUID
    task_type: str
    status: str
    message: str
    created_at: datetime | None = None


class ExtractionLogsPublic(SQLModel):
    data: list[ExtractionLogPublic]
    count: int


class AdminStats(SQLModel):
    pending_candidates: int
    subjects_count: int
    knowledge_points_count: int
    documents_total: int
    documents_processing: int
    documents_failed: int


# ==================== 教师图谱共建建议工单 ====================

class KnowledgeSuggestion(SQLModel, table=True):
    """教师在图谱使用中提交的共建建议工单（与 LLM 批量抽取的候选知识点表区分）。

    教师提交的全部是建议，审核通过后才由管理员动作写入 Neo4j；
    处理结果不实时推送教师（毕设简化，不做消息通知）。
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    kind: str = Field(max_length=50, index=True)  # missing_kp | correction | misconception | exam_point
    name: str = Field(max_length=255)
    subject: str = Field(default="通用", max_length=100)
    grade_level: str | None = Field(default=None, max_length=50)
    textbook_version: str | None = Field(default=None, max_length=200)
    chapter: str | None = Field(default=None, max_length=255)
    target_kp_id: str | None = Field(default=None, max_length=64)
    definition: str | None = Field(default=None, max_length=2000)
    suggestion: str | None = Field(default=None, max_length=2000)
    source: str = Field(default="teacher_suggest", max_length=50)  # teacher_suggest
    status: str = Field(default="pending", max_length=20, index=True)  # pending | approved | rejected
    submitter_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE")
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


class SuggestionCreate(SQLModel):
    kind: str = Field(max_length=50)  # missing_kp | correction | misconception | exam_point
    name: str = Field(min_length=1, max_length=255)
    subject: str = Field(default="通用", max_length=100)
    grade_level: str | None = Field(default=None, max_length=50)
    textbook_version: str | None = Field(default=None, max_length=200)
    chapter: str | None = Field(default=None, max_length=255)
    target_kp_id: str | None = Field(default=None, max_length=64)
    definition: str | None = Field(default=None, max_length=2000)
    suggestion: str | None = Field(default=None, max_length=2000)


class SuggestionPublic(SQLModel):
    id: uuid.UUID
    kind: str
    name: str
    subject: str
    grade_level: str | None = None
    textbook_version: str | None = None
    chapter: str | None = None
    target_kp_id: str | None = None
    definition: str | None = None
    suggestion: str | None = None
    source: str
    status: str
    submitter_id: uuid.UUID
    created_at: datetime | None = None
