import enum
import uuid
from datetime import datetime, timezone

from pydantic import EmailStr
from sqlalchemy import JSON, DateTime
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


# ==================== 多租户 / RBAC 枚举 ====================

class OrgType(str, enum.Enum):
    SCHOOL = "school"   # 学校租户
    REGION = "region"   # 区域租户（上级，可包含多所学校）


class Visibility(str, enum.Enum):
    PRIVATE = "private"   # 仅本人
    GROUP = "group"       # 组内（教研组）
    SCHOOL = "school"     # 本校
    REGION = "region"     # 本区域
    PUBLIC = "public"     # 全平台（跨租户，谨慎使用）


class LessonPlanStatus(str, enum.Enum):
    DRAFT = "draft"         # 草稿（仅本人可改）
    PENDING = "pending"     # 待审核
    APPROVED = "approved"   # 已通过
    REJECTED = "rejected"   # 已驳回
    ARCHIVED = "archived"   # 已归档


class LessonPlanSource(str, enum.Enum):
    PERSONAL = "个人教案"          # 个人教案
    COLLECTIVE = "集体备课产出"    # 集体备课产出
    KNOWLEDGE_BASE = "知识库沉淀"  # 知识库沉淀


class ResourceType(str, enum.Enum):
    LESSON_PLAN = "lesson_plan"
    TEMPLATE = "template"
    KNOWLEDGE_ITEM = "knowledge_item"


class GranteeType(str, enum.Enum):
    USER = "user"
    GROUP = "group"
    SCHOOL = "school"
    REGION = "region"


class AclPermission(str, enum.Enum):
    VIEW = "view"
    EDIT = "edit"


class ReviewAction(str, enum.Enum):
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    RESUBMIT = "resubmit"
    ARCHIVE = "archive"
    PUBLISH_KB = "publish_kb"


class ContributionType(str, enum.Enum):
    CREATE = "create"
    SUBMIT = "submit"
    APPROVE = "approve"
    REFERENCE = "reference"
    COMMENT = "comment"


# ==================== 组织 / 角色 / 权限 ====================

class Organization(SQLModel, table=True):
    """租户：学校或区域（区域为学校的上级，构成 org 树）"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=200, index=True)
    type: OrgType = Field(default=OrgType.SCHOOL)
    parent_id: uuid.UUID | None = Field(
        default=None, foreign_key="organization.id", ondelete="SET NULL"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


class Permission(SQLModel, table=True):
    """权限点（最小授权单元）"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    code: str = Field(max_length=100, unique=True, index=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=500)


class UserRole(SQLModel, table=True):
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, primary_key=True, ondelete="CASCADE")
    role_id: uuid.UUID = Field(foreign_key="role.id", nullable=False, primary_key=True, ondelete="CASCADE")


class Role(SQLModel, table=True):
    """角色 = 一组权限点。MVP：teacher / research_admin（超管临时兼任）"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    code: str = Field(max_length=100, unique=True, index=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=500)
    org_id: uuid.UUID | None = Field(
        default=None, foreign_key="organization.id", ondelete="CASCADE"
    )
    is_system: bool = Field(default=False)
    users: list["User"] = Relationship(link_model=UserRole, back_populates="roles")


class RolePermission(SQLModel, table=True):
    role_id: uuid.UUID = Field(foreign_key="role.id", nullable=False, primary_key=True, ondelete="CASCADE")
    permission_id: uuid.UUID = Field(foreign_key="permission.id", nullable=False, primary_key=True, ondelete="CASCADE")


# ==================== 资源共享例外（ACL） ====================

class ResourceAcl(SQLModel, table=True):
    """资源例外共享：在 visibility 之外，针对特定用户/组/校/区域授予 view/edit"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE")
    resource_type: ResourceType = Field(default=ResourceType.LESSON_PLAN)
    resource_id: uuid.UUID = Field(nullable=False, index=True)
    grantee_type: GranteeType = Field(default=GranteeType.USER)
    grantee_id: uuid.UUID = Field(nullable=False, index=True)
    permission: AclPermission = Field(default=AclPermission.VIEW)
    created_by: uuid.UUID = Field(foreign_key="user.id", nullable=False)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


# ==================== 审核记录 ====================

class ReviewRecord(SQLModel, table=True):
    """审核/状态流转记录（含驳回原因、可重新提交）"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE")
    resource_type: ResourceType = Field(default=ResourceType.LESSON_PLAN)
    resource_id: uuid.UUID = Field(nullable=False, index=True)
    reviewer_id: uuid.UUID = Field(foreign_key="user.id", nullable=False)
    action: ReviewAction = Field(default=ReviewAction.SUBMIT)
    from_status: str | None = Field(default=None, max_length=20)
    to_status: str | None = Field(default=None, max_length=20)
    comment: str | None = Field(default=None, max_length=2000)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


# ==================== 贡献事件 ====================

class ContributionEvent(SQLModel, table=True):
    """共建贡献事件（基于事件聚合周/月进度，防重复计数靠 dedupe_key）"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True, ondelete="CASCADE")
    org_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE")
    event_type: ContributionType = Field(default=ContributionType.CREATE, index=True)
    resource_type: ResourceType | None = Field(default=None)
    resource_id: uuid.UUID | None = Field(default=None, index=True)
    points: int = Field(default=1)
    period: str | None = Field(default=None, max_length=20, index=True)  # 如 2026-W43
    dedupe_key: str | None = Field(default=None, max_length=200, index=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


# ==================== 教案模板 ====================

class LessonPlanTemplate(SQLModel, table=True):
    """可复用教案骨架（按组织沉淀，入知识库的优质案例也可落为模板）"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE", index=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    title: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=100)
    grade_level: GradeLevel | None = Field(default=None)
    teaching_objectives: str | None = Field(default=None)
    teaching_process: str | None = Field(default=None)
    subject_id: uuid.UUID | None = Field(default=None, foreign_key="subject.id", ondelete="SET NULL")
    visibility: Visibility = Field(default=Visibility.SCHOOL)
    status: LessonPlanStatus = Field(default=LessonPlanStatus.APPROVED)
    source_type: LessonPlanSource = Field(default=LessonPlanSource.KNOWLEDGE_BASE)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


# ==================== 教案版本快照（知识库引用，不复制正文） ====================

class LessonPlanVersionSnapshot(SQLModel, table=True):
    """教案审核通过/入知识库时的冻结快照，知识库条目只引用它，不直接存正文"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lesson_plan_id: uuid.UUID = Field(foreign_key="lessonplan.id", nullable=False, index=True, ondelete="CASCADE")
    org_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE")
    version: int = Field(default=1)
    snapshot_json: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


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
    org_id: uuid.UUID | None = None  # 由管理员分配，注册流程可不传


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)
    org_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None


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
    org_id: uuid.UUID | None = Field(
        default=None, foreign_key="organization.id", ondelete="SET NULL", index=True
    )
    group_id: uuid.UUID | None = Field(default=None, index=True)  # 所属教研组（可空，MVP 不启用教研组长）
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    roles: list["Role"] = Relationship(link_model=UserRole, back_populates="users")
    lesson_plans: list["LessonPlan"] = Relationship(back_populates="owner", cascade_delete=True)
    documents: list["Document"] = Relationship(back_populates="owner", cascade_delete=True)
    ppt_records: list["PptRecord"] = Relationship(back_populates="owner", cascade_delete=True)
    schedules: list["Schedule"] = Relationship(back_populates="owner", cascade_delete=True)
    tasks: list["Task"] = Relationship(back_populates="owner", cascade_delete=True)
    subjects: list["Subject"] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    org_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    created_at: datetime | None = None
    roles: list[str] = []  # 角色 code 列表（便于前端菜单/权限判断）


class UsersPublic(SQLModel):
    data: list[UserPublic]
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
      org_id: uuid.UUID | None = Field(
          default=None, foreign_key="organization.id", ondelete="CASCADE", index=True
      )
      group_id: uuid.UUID | None = Field(default=None, index=True)
      visibility: Visibility = Field(default=Visibility.PRIVATE)
      status: LessonPlanStatus = Field(default=LessonPlanStatus.DRAFT)
      source_type: LessonPlanSource = Field(default=LessonPlanSource.PERSONAL)
      template_id: uuid.UUID | None = Field(
          default=None, foreign_key="lessonplantemplate.id", ondelete="SET NULL"
      )
      version: int = Field(default=1)
      subject_id: uuid.UUID | None = Field(default=None, foreign_key="subject.id", ondelete="SET NULL")
      extracted_text: str | None = Field(default=None)
      style: str | None = Field(default=None, max_length=50)
      # 关联的知识点 ID 列表（指向 Neo4j KnowledgePoint 节点）
      knowledge_point_ids: list[str] = Field(default_factory=list, sa_type=JSON)
      # 教案校验报告（固定流水线 verify 节点输出）
      verification_report: dict | None = Field(default=None, sa_type=JSON)
      # 课堂习题（教师备课时录入，作为「一键生成作业」的初始题目来源）
      # 每项为 dict：{ id, type, stem, options, correct_option, answers, reference_answer }
      classroom_exercises: list[dict] = Field(default_factory=list, sa_type=JSON)


class LessonPlanCreate(SQLModel):
    """创建教案请求体"""
    title: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=100)
    grade_level: GradeLevel | None = None
    teaching_objectives: str | None = None
    teaching_process: str | None = None
    knowledge_point_ids: list[str] = []
    subject_id: str | None = None
    visibility: Visibility = Visibility.PRIVATE
    source_type: LessonPlanSource = LessonPlanSource.PERSONAL
    group_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None


class LessonPlanUpdate(SQLModel):
    """更新教案请求体（status 走状态机专用端点，不在此处修改）"""
    title: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str | None = Field(default=None, min_length=1, max_length=100)
    grade_level: GradeLevel | None = None
    teaching_objectives: str | None = None
    teaching_process: str | None = None
    knowledge_point_ids: list[str] | None = None
    group_id: uuid.UUID | None = None
    visibility: Visibility | None = None
    source_type: LessonPlanSource | None = None
    classroom_exercises: list[dict] | None = None


class LessonPlanPublic(LessonPlanBase):
    """教案返回体（knowledge_points 从 Neo4j 按 ID 拉取）"""
    id: uuid.UUID
    owner_id: uuid.UUID
    org_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    visibility: Visibility = Visibility.PRIVATE
    status: LessonPlanStatus = LessonPlanStatus.DRAFT
    source_type: LessonPlanSource = LessonPlanSource.PERSONAL
    template_id: uuid.UUID | None = None
    version: int = 1
    subject_id: str | None = None
    created_at: datetime | None = None
    knowledge_point_ids: list[str] = []
    knowledge_points: list[KnowledgePointOut] = []
    classroom_exercises: list[dict] = []


class LessonPlansPublic(SQLModel):
      """教案列表返回体"""
      data: list[LessonPlanPublic]
      count: int


# ==================== 作业 / 提交 ====================

class HomeworkStatus(str, enum.Enum):
    DRAFT = "draft"         # 草稿（可编辑）
    PUBLISHED = "published"  # 已发布（生成提交入口）
    CLOSED = "closed"        # 已关闭


class QuestionType(str, enum.Enum):
    CHOICE = "choice"  # 选择
    FILL = "fill"      # 填空
    SHORT = "short"    # 简答
    ESSAY = "essay"    # 论述


class SubmissionStatus(str, enum.Enum):
    SUBMITTED = "submitted"  # 已提交
    GRADED = "graded"  # 已自动判分（客观题已判 / 主观题已给建议，待教师终评）


class HomeworkQuestion(SQLModel):
    """作业单题（作为 Homework.questions JSON 数组中的元素，不直接建表）。

    - type: 选择/填空/简答/论述
    - knowledge_point_ids: 每题必选 ≥1 个关联知识点（发布时校验）
    - options / correct_option: 选择题专用
    - answers: 填空题多解（支持多个正确答案）
    - reference_answer: 简答/论述参考答案
    """
    id: str
    type: QuestionType
    stem: str
    knowledge_point_ids: list[str] = []
    options: list[str] = []               # 选择题选项
    correct_option: int | None = None     # 选择题正确选项索引
    answers: list[str] = []               # 填空题多解
    reference_answer: str = ""            # 简答/论述参考答案
    score: float = Field(default=5.0, description="本题满分（默认 5 分）")


class HomeworkBase(SQLModel):
    title: str = Field(min_length=1, max_length=255, description="作业标题")
    knowledge_point_ids: list[str] = Field(
        default_factory=list, sa_type=JSON, description="作业知识点题库（继承教案 + 可扩充）"
    )
    questions: list[HomeworkQuestion] = Field(
        default_factory=list, sa_type=JSON, description="题目列表"
    )


class Homework(HomeworkBase, table=True):
    """作业表。题目以 JSON 数组存储，便于整体编辑与版本快照。"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lesson_plan_id: uuid.UUID | None = Field(
        default=None, foreign_key="lessonplan.id", ondelete="SET NULL", index=True
    )
    org_id: uuid.UUID | None = Field(
        default=None, foreign_key="organization.id", ondelete="CASCADE", index=True
    )
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    status: HomeworkStatus = Field(default=HomeworkStatus.DRAFT)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


class HomeworkCreate(HomeworkBase):
    """创建空白作业请求体"""
    lesson_plan_id: str | None = None


class HomeworkUpdate(SQLModel):
    """更新作业请求体（字段均可选，部分更新）"""
    title: str | None = Field(default=None, min_length=1, max_length=255)
    knowledge_point_ids: list[str] | None = None
    questions: list[HomeworkQuestion] | None = None


class HomeworkPublic(HomeworkBase):
    id: uuid.UUID
    lesson_plan_id: uuid.UUID | None = None
    owner_id: uuid.UUID
    org_id: uuid.UUID | None = None
    status: HomeworkStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # 知识点题库解析（来自 Neo4j，供前端选择器使用）
    knowledge_points: list[KnowledgePointOut] = []


class HomeworksPublic(SQLModel):
    data: list[HomeworkPublic]
    count: int


class Submission(SQLModel, table=True):
    """学生提交记录。本期以「模拟提交 / 教师代录」实现，不依赖学生端。

    - student_id 明文仅在入参出现，落库存储为哈希（student_id_hash）
    - answers: 学生作答，元素 { question_id, content }
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    homework_id: uuid.UUID = Field(
        foreign_key="homework.id", nullable=False, ondelete="CASCADE", index=True
    )
    org_id: uuid.UUID | None = Field(
        default=None, foreign_key="organization.id", ondelete="CASCADE", index=True
    )
    student_id_hash: str = Field(max_length=128, index=True)  # 学号哈希存储
    answers: list[dict] = Field(default_factory=list, sa_type=JSON)
    status: SubmissionStatus = Field(default=SubmissionStatus.SUBMITTED)
    # PRD §7④：同一学生重复提交以最后一次为准，旧版本标记 superseded（不物理删除，保留留痕）
    superseded: bool = Field(default=False, description="True=已被该学生的后续提交覆盖")
    submitted_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
    graded_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True), description="自动判分完成时间"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


class SimulateSubmitRequest(SQLModel):
    """模拟提交 / 教师代录入参（学号为明文，落库转哈希）"""
    student_id: str = Field(min_length=1, max_length=64, description="学号（明文入参，存储为哈希）")
    answers: list[dict] = Field(default_factory=list, description="学生作答 [{question_id, content}]")


class SubmissionPublic(SQLModel):
    id: uuid.UUID
    homework_id: uuid.UUID
    student_id_hash: str
    answers: list[dict] = []
    status: SubmissionStatus
    superseded: bool = False  # True=已被后续提交覆盖（PRD §7④）
    submitted_at: datetime | None = None
    created_at: datetime | None = None


class SubmissionsPublic(SQLModel):
    data: list[SubmissionPublic]
    count: int


# ==================== 判分 / 批改（FR-04/05/06） ====================
# 客观题自动判分（规则 + 标准答案）、主观题 AI 辅助建议、教师终评


class QuestionGradeStatus(str, enum.Enum):
    PENDING = "pending"  # 待判分
    AUTO_GRADED = "auto_graded"  # 已自动判分 / 已给 AI 建议，待教师终评
    FINALIZED = "finalized"  # 教师已确认终评（不可逆）


class SubmissionGrade(SQLModel, table=True):
    """每题判分记录（一题一行，挂在 Submission 下）。

    - 客观题：is_correct / auto_score / auto_detail（判分依据，可溯源）
    - 主观题：ai_suggested_score / ai_comment / ai_knowledge_points / ai_confidence /
              needs_human（置信度 < 0.7 强制"建议人工"）
    - 教师终评（FR-06）：final_score / final_comment / finalized（不可逆）
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    submission_id: uuid.UUID = Field(
        foreign_key="submission.id", nullable=False, ondelete="CASCADE", index=True
    )
    question_id: str = Field(max_length=64, index=True)
    question_type: QuestionType
    full_score: float = Field(default=0.0, description="本题满分")

    # 客观题判分结果
    is_correct: bool | None = None
    auto_score: float | None = None
    auto_detail: str | None = None  # 判分依据 / 溯源说明

    # 主观题 AI 辅助建议（FR-05）
    ai_suggested_score: float | None = None
    ai_comment: str | None = None
    ai_knowledge_points: list[str] = Field(
        default_factory=list, sa_type=JSON, description="AI 判定命中的知识点 ID"
    )
    ai_confidence: float | None = None
    needs_human: bool = Field(default=False)  # 置信度 < 0.7 强制"建议人工"
    # PRD §7①：AI 调用失败（超时/异常）时显式标记，避免把启发式兜底误认为真实 AI 结论
    ai_unavailable: bool = Field(default=False, description="True=AI 不可用，已转人工")

    # 教师终评（FR-06）
    final_score: float | None = None
    final_comment: str | None = None
    finalized: bool = Field(default=False)
    finalized_at: datetime | None = None

    status: QuestionGradeStatus = Field(default=QuestionGradeStatus.PENDING)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


class QuestionGradePublic(SQLModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    question_id: str
    question_type: QuestionType
    full_score: float
    is_correct: bool | None = None
    auto_score: float | None = None
    auto_detail: str | None = None
    ai_suggested_score: float | None = None
    ai_comment: str | None = None
    ai_knowledge_points: list[str] = []
    ai_confidence: float | None = None
    needs_human: bool = False
    ai_unavailable: bool = False  # PRD §7① AI 不可用，转人工
    final_score: float | None = None
    final_comment: str | None = None
    finalized: bool = False
    finalized_at: datetime | None = None
    status: QuestionGradeStatus


class SubmissionGradesPublic(SQLModel):
    data: list[QuestionGradePublic]
    count: int
    submission_status: str | None = None


class FinalizeGradeRequest(SQLModel):
    """教师终评请求（FR-06）。

    - adopt_suggestion=True：一键采纳 AI 建议（final_score / final_comment 取 AI 建议值）
    - 否则以 final_score + final_comment 落库（手动改分 + 写评语）
    - confirm=True：前端二次确认弹窗后置位，后端据此放行不可逆写库
    """

    final_score: float | None = None
    final_comment: str | None = None
    adopt_suggestion: bool = False
    confirm: bool = Field(default=False, description="二次确认开关（前端弹窗确认后置 True）")


class GradeTriggerResponse(SQLModel):
    submission_id: uuid.UUID
    graded_count: int
    grades: list[QuestionGradePublic]
    message: str = ""


class LabeledSetReport(SQLModel):
    """FR-04 标注集验收报告：客观题自动判分准确率与错判溯源。"""

    total: int
    correct: int
    accuracy: float
    threshold: float = 0.95
    passed: bool
    misjudged: list[dict] = Field(default_factory=list)


# ==================== FR-07 错误聚合看板 ====================


class ErrorStatScope(str, enum.Enum):
    CLASS = "class"  # 班级视角（整份作业全部提交）
    PERSONAL = "personal"  # 个人视角（某一学生的提交）


class ErrorPattern(SQLModel):
    """高频错误模式：一种错误表述及其出现次数与来源题目。"""

    expression: str
    count: int
    question_ids: list[str] = Field(default_factory=list)


class KnowledgePointErrorStat(SQLModel):
    """单个关联知识点的错误聚合结果。

    FR-07 要求覆盖全部关联知识点：即便某知识点无人作答（graded_count=0），
    也必须以 error_rate=0 出现，确保「无遗漏」。
    """

    knowledge_point_id: str
    knowledge_point_name: str | None = None
    question_count: int = 0  # 该知识点关联的题目数
    graded_count: int = 0  # 已批改题次数
    wrong_count: int = 0
    error_rate: float = 0.0
    # PRD §7⑤：知识点已被删除（图谱中查不到）→ False，看板标「已失效」且不计入活跃统计
    is_active: bool = True
    top_patterns: list[ErrorPattern] = Field(default_factory=list)


class ErrorDashboard(SQLModel):
    homework_id: uuid.UUID
    homework_title: str = ""
    scope: ErrorStatScope
    submission_id: uuid.UUID | None = None
    total_submissions: int = 0
    graded_submissions: int = 0
    knowledge_points: list[KnowledgePointErrorStat] = Field(default_factory=list)
    knowledge_point_total: int = 0  # 全部关联知识点数（用于"无遗漏"校验）


# ==================== FR-08 误区回流 ====================


class MisconceptionSuggestion(SQLModel):
    knowledge_point_id: str
    knowledge_point_name: str | None = None
    error_rate: float
    wrong_count: int
    graded_count: int
    threshold: float
    typical_expressions: list[str] = Field(default_factory=list)
    suggested_content: str = ""
    suggested_correction: str = ""


class MisconceptionSuggestions(SQLModel):
    data: list[MisconceptionSuggestion]
    count: int
    threshold: float


class BackflowConfirmRequest(SQLModel):
    """教师确认回流：写入知识点误区 + 纠正，来源标注"教学回流"。"""

    knowledge_point_id: str
    content: str
    correction: str = ""


class MisconceptionOut(SQLModel):
    id: str
    content: str
    correction: str = ""
    source: str = "manual"


class MistakeFeedbackStatus(str, enum.Enum):
    """PRD §9 R-2：误区回流决策三态（留痕 + 幂等依据）。"""

    PENDING = "pending"  # 已生成建议，待教师决策
    CONFIRMED = "confirmed"  # 已采纳并写入图谱
    REJECTED = "rejected"  # 已驳回


class MistakeFeedback(SQLModel, table=True):
    """误区回流决策留痕表（幂等键：homework_id + knowledge_point_id + content）。

    同一条建议被重复确认时，命中已有 CONFIRMED 记录即直接返回，不再重复写入图谱。
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    homework_id: uuid.UUID = Field(
        foreign_key="homework.id", nullable=False, ondelete="CASCADE", index=True
    )
    knowledge_point_id: str = Field(max_length=128, index=True)
    content: str = Field(max_length=500)
    correction: str = Field(default="", max_length=500)
    misconception_id: str = Field(default="", max_length=128, description="图谱误区节点 ID")
    status: MistakeFeedbackStatus = Field(default=MistakeFeedbackStatus.PENDING)
    decided_by: uuid.UUID | None = Field(default=None, foreign_key="user.id")
    decided_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


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
    subject: str = Field(min_length=1, max_length=200, description="科目名称，不可为空")
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
    title: str = Field(min_length=1, max_length=500, description="任务标题，不可为空")
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
    name: str = Field(min_length=1, max_length=200, description="学科名称，不可为空")
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
    name: str = Field(min_length=1, max_length=500)
    version: str | None = None
    grade_level: str | None = None
    cover_url: str | None = None
    description: str | None = None
    # 用 UUID 类型而非 str：非法 UUID 由 pydantic 拦截返回 422，
    # 避免 uuid.UUID() 在路由内抛未捕获 ValueError 造成 500。
    subject_id: uuid.UUID

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
    review_note: str | None = Field(default=None, max_length=2000)  # 驳回/处理理由（管理员填写，回推教师）


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
    review_note: str | None = None


# ==================== 组织 / 角色 / 权限 返回体 ====================

class OrganizationPublic(SQLModel):
    id: uuid.UUID
    name: str
    type: OrgType
    parent_id: uuid.UUID | None = None
    created_at: datetime | None = None


class OrganizationsPublic(SQLModel):
    data: list[OrganizationPublic]
    count: int


class PermissionPublic(SQLModel):
    code: str
    name: str
    description: str | None = None


class PermissionsPublic(SQLModel):
    data: list[PermissionPublic]


class RolePublic(SQLModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    org_id: uuid.UUID | None = None
    is_system: bool = False
    permissions: list[str] = []  # 权限点 code 列表


class RolesPublic(SQLModel):
    data: list[RolePublic]
    count: int


# ==================== 资源共享例外（ACL） ====================

class ResourceAclCreate(SQLModel):
    resource_type: ResourceType = ResourceType.LESSON_PLAN
    resource_id: uuid.UUID
    grantee_type: GranteeType = GranteeType.USER
    grantee_id: uuid.UUID
    permission: AclPermission = AclPermission.VIEW


class ResourceAclPublic(SQLModel):
    id: uuid.UUID
    org_id: uuid.UUID
    resource_type: ResourceType
    resource_id: uuid.UUID
    grantee_type: GranteeType
    grantee_id: uuid.UUID
    permission: AclPermission
    created_at: datetime | None = None


class ResourceAclsPublic(SQLModel):
    data: list[ResourceAclPublic]
    count: int


# ==================== 审核记录 返回体 ====================

class ReviewRecordPublic(SQLModel):
    id: uuid.UUID
    org_id: uuid.UUID
    resource_type: ResourceType
    resource_id: uuid.UUID
    reviewer_id: uuid.UUID
    action: ReviewAction
    from_status: str | None = None
    to_status: str | None = None
    comment: str | None = None
    created_at: datetime | None = None


class ReviewRecordsPublic(SQLModel):
    data: list[ReviewRecordPublic]
    count: int


# ==================== 贡献事件 返回体 ====================

class ContributionEventPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    org_id: uuid.UUID
    event_type: ContributionType
    resource_type: ResourceType | None = None
    resource_id: uuid.UUID | None = None
    points: int
    period: str | None = None
    created_at: datetime | None = None


class ContributionsMe(SQLModel):
    """我的共建贡献进度（基于 contribution_event 聚合）"""
    period: str
    total_points: int
    events_count: int
    goal_points: int = 0
    progress: float = 0.0  # 0~1
    breakdown: dict = {}    # event_type -> 次数


# ==================== 教案模板 返回体 ====================

class LessonPlanTemplateCreate(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=100)
    grade_level: GradeLevel | None = None
    teaching_objectives: str | None = None
    teaching_process: str | None = None
    subject_id: str | None = None
    visibility: Visibility = Visibility.SCHOOL
    source_type: LessonPlanSource = LessonPlanSource.KNOWLEDGE_BASE


class LessonPlanTemplatePublic(SQLModel):
    id: uuid.UUID
    org_id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    subject: str
    grade_level: GradeLevel | None = None
    visibility: Visibility = Visibility.SCHOOL
    status: LessonPlanStatus = LessonPlanStatus.APPROVED
    source_type: LessonPlanSource = LessonPlanSource.KNOWLEDGE_BASE
    created_at: datetime | None = None


class LessonPlanTemplatesPublic(SQLModel):
    data: list[LessonPlanTemplatePublic]
    count: int


class LessonPlanVersionSnapshotPublic(SQLModel):
    id: uuid.UUID
    lesson_plan_id: uuid.UUID
    org_id: uuid.UUID
    version: int
    created_at: datetime | None = None
    snapshot_json: dict = {}


# ==================== 新 Dashboard 契约 ====================

class ScenarioCard(SQLModel):
    """配置化场景卡：按组织类型/人群标签/权限显示，点击带筛选进入对应页"""
    id: str
    title: str
    description: str
    icon: str | None = None
    target: str                      # 目标路由
    required_permissions: list[str] = []  # 无权限则不显示
    audience_tags: list[str] = []    # 人群标签（如 teacher / research_admin）


class MyLessonPlan(SQLModel):
    """我的教案聚合卡片（含后端统一计算的完整度）"""
    id: uuid.UUID
    title: str
    subject: str
    grade_level: GradeLevel | None = None
    status: LessonPlanStatus = LessonPlanStatus.DRAFT
    visibility: Visibility = Visibility.PRIVATE
    completeness_score: int = 0
    missing_sections: list[str] = []
    updated_at: datetime | None = None


class DashboardSummary(SQLModel):
    """/dashboard/summary 聚合返回"""
    scenario_cards: list[ScenarioCard] = []
    my_lesson_plans: list[MyLessonPlan] = []
    my_contributions: ContributionsMe | None = None
    stats: dict = {}
