"""教案的可见性 / 编辑权限判定（组织隔离 + visibility + ACL 例外）。

规则（见产品规格验收）：
- A 校用户看不到 B 校资源（org 作用域）。
- 组内共享仅组员可见（group_id 匹配）。
- 教师只能改自己草稿。
- resource_acl 处理可见性之外的例外共享。
"""
from sqlmodel import Session, select

from app.core.rbac import org_chain
from app.models import (
    AclPermission,
    GranteeType,
    LessonPlan,
    LessonPlanStatus,
    ResourceAcl,
    ResourceType,
    User,
    Visibility,
)


def _acl_permissions(
    session: Session, user: User, resource_type: ResourceType, resource_id
) -> set[AclPermission]:
    """计算用户对某资源的 ACL 授权集合（view / edit）。"""
    rows = session.exec(
        select(ResourceAcl).where(
            ResourceAcl.resource_type == resource_type,
            ResourceAcl.resource_id == resource_id,
        )
    ).all()
    if not rows:
        return set()
    chain = org_chain(session, user.org_id) if user.org_id else []
    granted: set[AclPermission] = set()
    for acl in rows:
        match = False
        if acl.grantee_type == GranteeType.USER and acl.grantee_id == user.id:
            match = True
        elif (
            acl.grantee_type == GranteeType.GROUP
            and user.group_id
            and acl.grantee_id == user.group_id
        ):
            match = True
        elif acl.grantee_type == GranteeType.SCHOOL and user.org_id and acl.grantee_id == user.org_id:
            match = True
        elif (
            acl.grantee_type == GranteeType.REGION
            and user.org_id
            and acl.grantee_id in chain
        ):
            match = True
        if match:
            granted.add(acl.permission)
    return granted


def can_view_lesson_plan(session: Session, user: User, lp: LessonPlan) -> bool:
    if user.is_superuser:
        return True
    if lp.owner_id == user.id:
        return True
    if _acl_permissions(session, user, ResourceType.LESSON_PLAN, lp.id):
        return True
    if lp.visibility == Visibility.PUBLIC:
        return True
    if user.org_id is None:
        return False
    chain = org_chain(session, user.org_id)
    if lp.visibility == Visibility.SCHOOL and lp.org_id == user.org_id:
        return True
    if lp.visibility == Visibility.REGION and lp.org_id in chain:
        return True
    if (
        lp.visibility == Visibility.GROUP
        and lp.group_id
        and lp.group_id == user.group_id
    ):
        return True
    return False


def can_edit_lesson_plan(session: Session, user: User, lp: LessonPlan) -> bool:
    if user.is_superuser:
        return True
    if lp.owner_id == user.id and lp.status == LessonPlanStatus.DRAFT:
        return True
    if AclPermission.EDIT in _acl_permissions(
        session, user, ResourceType.LESSON_PLAN, lp.id
    ):
        return True
    return False


def lesson_plan_candidate_filter(session: Session, user: User):
    """列表/统计的候选范围：组织链 + 公开 + ACL 例外。

    返回 SQLAlchemy 布尔表达式； fine-grained 可见性（private/group 内部）由 can_view 二次过滤。
    """
    from sqlmodel import or_

    if user.is_superuser:
        return None  # 平台超管看全部
    if user.org_id is None:
        # 无组织用户仅能看到自己创建的（owner_id 由 can_view 处理）；此处返回永假不影响
        return LessonPlan.owner_id == user.id
    chain = org_chain(session, user.org_id)
    conditions = [
        LessonPlan.org_id.in_(chain),  # type: ignore[arg-type]
        LessonPlan.visibility == Visibility.PUBLIC,
    ]
    acl_ids = session.exec(
        select(ResourceAcl.resource_id).where(
            ResourceAcl.resource_type == ResourceType.LESSON_PLAN,
            _acl_resource_match(session, user),
        )
    ).all()
    if acl_ids:
        conditions.append(LessonPlan.id.in_(acl_ids))  # type: ignore[arg-type]
    return or_(*conditions)


def _acl_resource_match(session: Session, user: User):
    """构造 ACL 行的 grantee 匹配表达式（用于列表范围）。"""
    from sqlmodel import or_

    chain = org_chain(session, user.org_id) if user.org_id else []
    conds = [
        (ResourceAcl.grantee_type == GranteeType.USER) & (ResourceAcl.grantee_id == user.id),
    ]
    if user.group_id:
        conds.append(
            (ResourceAcl.grantee_type == GranteeType.GROUP) & (ResourceAcl.grantee_id == user.group_id)
        )
    if user.org_id:
        conds.append(
            (ResourceAcl.grantee_type == GranteeType.SCHOOL) & (ResourceAcl.grantee_id == user.org_id)
        )
        if chain:
            conds.append(
                (ResourceAcl.grantee_type == GranteeType.REGION) & (ResourceAcl.grantee_id.in_(chain))  # type: ignore[arg-type]
            )
    return or_(*conds)
