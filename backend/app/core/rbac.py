"""RBAC 核心：权限点 + 角色 + 数据范围。

设计原则（见产品规格）：
- 用「权限点 + 本人/本组/本校/本区域」做授权，而非写死「超管=教研管理员」。
- MVP 中超管（is_superuser）临时兼任「教研管理员」权限组，可审核/设共享/管知识库；
  后续拆出教研组长角色时，只需新增角色并授权，无需改业务代码。
- 权限点至少覆盖：创建教案、提交审核、组内共享、校本共享、审核、知识库管理、
  组织管理、查看统计。
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

# ===================== 权限点（最小授权单元） =====================
PERM_CREATE_LESSON_PLAN = "lesson_plan:create"   # 创建教案
PERM_SUBMIT_REVIEW = "lesson_plan:submit"         # 提交审核
PERM_SHARE_GROUP = "share:group"                  # 组内共享
PERM_SHARE_SCHOOL = "share:school"                # 校本共享
PERM_REVIEW = "review"                            # 审核
PERM_KB_MANAGE = "kb:manage"                      # 知识库管理
PERM_ORG_MANAGE = "org:manage"                    # 组织管理（含角色/成员）
PERM_VIEW_STATS = "stats:view"                    # 查看统计

# 平台超级管理员（is_superuser）拥有全部权限点
ALL_PERMISSIONS = [
    PERM_CREATE_LESSON_PLAN,
    PERM_SUBMIT_REVIEW,
    PERM_SHARE_GROUP,
    PERM_SHARE_SCHOOL,
    PERM_REVIEW,
    PERM_KB_MANAGE,
    PERM_ORG_MANAGE,
    PERM_VIEW_STATS,
]

# ===================== 默认角色（MVP） =====================
# 角色枚举预留：教师、骨干教师（用标签/能力，不做权限角色）、教研组长（MVP 不启用）、
# 教研员/教研管理员、超管。
# 注意：「超管兼任教研管理员」为临时方案，MVP 通过把首个超管绑定 research_admin 角色实现；
# 后续拆出教研组长，只需新增 ROLE_RESEARCH_LEAD 并授权，业务代码无需改动。
ROLE_TEACHER = "teacher"
ROLE_RESEARCH_ADMIN = "research_admin"   # 教研管理员（MVP 由超管兼任）
ROLE_RESEARCH_LEAD = "research_lead"     # 教研组长（预留，MVP 不启用）

DEFAULT_ROLES: dict[str, dict] = {
    ROLE_TEACHER: {
        "name": "教师",
        "permissions": [PERM_CREATE_LESSON_PLAN, PERM_SUBMIT_REVIEW],
    },
    ROLE_RESEARCH_ADMIN: {
        "name": "教研管理员",
        "permissions": [
            PERM_CREATE_LESSON_PLAN,
            PERM_SUBMIT_REVIEW,
            PERM_SHARE_GROUP,
            PERM_SHARE_SCHOOL,
            PERM_REVIEW,
            PERM_KB_MANAGE,
            PERM_VIEW_STATS,
        ],
    },
    # 预留：教研组长（负责组内审核与共享），MVP 不启用
    ROLE_RESEARCH_LEAD: {
        "name": "教研组长",
        "permissions": [
            PERM_CREATE_LESSON_PLAN,
            PERM_SUBMIT_REVIEW,
            PERM_SHARE_GROUP,
            PERM_REVIEW,
        ],
    },
}


def get_user_permissions(session: Session, user: User) -> set[str]:
    """返回用户拥有的全部权限点 code 集合（合并其所有角色）。"""
    if user.is_superuser:
        return set(ALL_PERMISSIONS)
    role_ids = session.exec(
        select(UserRole.role_id).where(UserRole.user_id == user.id)
    ).all()
    if not role_ids:
        return set()
    perm_ids = session.exec(
        select(RolePermission.permission_id).where(
            RolePermission.role_id.in_(role_ids)  # type: ignore[arg-type]
        )
    ).all()
    codes = session.exec(
        select(Permission.code).where(Permission.id.in_(perm_ids))  # type: ignore[arg-type]
    ).all()
    return set(codes)


def user_has_permission(session: Session, user: User, code: str) -> bool:
    if user.is_superuser:
        return True
    return code in get_user_permissions(session, user)


def get_user_role_codes(session: Session, user: User) -> list[str]:
    if user.is_superuser:
        return [ROLE_RESEARCH_ADMIN]
    ids = session.exec(
        select(UserRole.role_id).where(UserRole.user_id == user.id)
    ).all()
    roles = session.exec(select(Role).where(Role.id.in_(ids))).all()  # type: ignore[arg-type]
    return [r.code for r in roles]


def require_permission(code: str):
    """返回 FastAPI 依赖：检查当前用户是否拥有指定权限点，否则 403。

    平台超级管理员（is_superuser）默认拥有全部权限。
    """

    def _dep(
        current_user: CurrentUser, session: SessionDep
    ) -> User:
        if not user_has_permission(session, current_user, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足：需要 {code}",
            )
        return current_user

    return _dep


# 常用依赖（直接作为 Depends 参数）
RequireCreateLessonPlan = Annotated[
    User, Depends(require_permission(PERM_CREATE_LESSON_PLAN))
]
RequireReview = Annotated[User, Depends(require_permission(PERM_REVIEW))]
RequireKbManage = Annotated[User, Depends(require_permission(PERM_KB_MANAGE))]
RequireOrgManage = Annotated[User, Depends(require_permission(PERM_ORG_MANAGE))]


def org_chain(session: Session, org_id) -> list:
    """返回 org 及其所有祖先（含自身），用于 region 级可见性与区域数据范围。"""
    chain: list = []
    cur = org_id
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        org = session.get(Organization, cur)
        cur = org.parent_id if org else None
    return chain


# 为类型检查器保留别名（避免循环导入时 IDE 报红）
_CurrentUser = CurrentUser
_SessionDep = SessionDep
