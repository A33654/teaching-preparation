# -*- coding: utf-8 -*-
"""L0 单元测试：密码哈希 / JWT 令牌 / RBAC 权限（纯逻辑，无外部服务）。"""
from __future__ import annotations

import time
from datetime import timedelta

import jwt
import pytest

from sqlmodel import select

from app.core import security
from app.core.config import settings
from app.core.rbac import (
    ALL_PERMISSIONS,
    PERM_REVIEW,
    get_user_permissions,
    user_has_permission,
)


class TestPasswordHashing:
    """正常 / 空白 / 错误 / 边界。

    注意：verify_password 的真实契约是 pwdlib 的 verify_and_update，
    返回 tuple[bool, str | None] = (是否匹配, 若哈希需升级则的新哈希或 None)。
    所有业务代码（crud.authenticate / users.py / login.py）均按
    `verified, _ = verify_password(...)` 解包；测试须匹配同一契约，
    不得假设其返回裸 bool（元组永远为真，误用会导致「恒为已认证」安全漏洞）。
    """

    def test_hash_verify_roundtrip(self):
        """✅ 正常：哈希后可正确校验"""
        hashed = security.get_password_hash("teacher123456")
        assert hashed != "teacher123456"
        verified, _ = security.verify_password("teacher123456", hashed)
        assert verified is True
        # 第二元素应为 None（argon2 哈希无需升级）
        assert _ is None

    def test_wrong_password_rejected(self):
        """❌ 错误：错误密码返回 (False, ...)"""
        hashed = security.get_password_hash("correct-horse")
        verified, _ = security.verify_password("wrong-battery", hashed)
        assert verified is False

    def test_empty_password_handled(self):
        """🈳 空白值：空密码不应抛未捕获异常"""
        hashed = security.get_password_hash("")
        # 空明文 vs 空哈希：只要不崩溃且第一元素为布尔即可
        verified, _ = security.verify_password("", hashed)
        assert isinstance(verified, bool)
        assert verified is True  # 空串哈希后校验空串应通过

    def test_long_password_boundary(self):
        """⚠️ 边界：超长密码（1 万字符）仍能哈希与校验"""
        long_pwd = "x" * 10_000
        hashed = security.get_password_hash(long_pwd)
        verified, _ = security.verify_password(long_pwd, hashed)
        assert verified is True

    def test_unicode_password(self):
        """⚠️ 边界：中文/Unicode 密码"""
        pwd = "中文密码🔐"
        hashed = security.get_password_hash(pwd)
        verified, _ = security.verify_password(pwd, hashed)
        assert verified is True


class TestAccessToken:
    def test_token_is_decodable(self):
        """✅ 正常：令牌可解码且含 sub"""
        token = security.create_access_token("user-123", timedelta(minutes=5))
        assert isinstance(token, str) and token
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        assert str(payload["sub"]) == "user-123"

    def test_expired_token_raises(self):
        """❌ 错误：过期令牌解码应抛异常（鉴权据此返回 401）"""
        token = security.create_access_token("user-123", timedelta(seconds=-1))
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])

    def test_tampered_token_raises(self):
        """❌ 错误：篡改令牌应解码失败"""
        token = security.create_access_token("user-123", timedelta(minutes=5))
        with pytest.raises(jwt.InvalidTokenError):
            jwt.decode(token + "tampered", settings.SECRET_KEY, algorithms=[security.ALGORITHM])

    def test_expiry_near_boundary(self):
        """⚠️ 边界：极短有效期（1 秒）令牌先可用、随后过期"""
        token = security.create_access_token("u", timedelta(seconds=1))
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        assert payload["sub"] == "u"
        time.sleep(1.2)
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])


class TestRBAC:
    def test_superuser_has_all_permissions(self, db):
        """✅ 正常：超管拥有全部权限点"""
        from app.models import User

        su = db.exec(select(User).where(User.is_superuser.is_(True))).first()
        assert su is not None, "测试库应存在超管"
        perms = get_user_permissions(db, su)
        assert set(ALL_PERMISSIONS).issubset(perms)
        assert user_has_permission(db, su, PERM_REVIEW) is True

    def test_new_user_no_permissions(self, db):
        """🈳 空白值：无角色用户无任何权限点"""
        from app import crud
        from app.models import UserCreate

        user = crud.get_user_by_email(session=db, email="qa_teacher@example.com")
        if user is None:
            user = crud.create_user(
                session=db,
                user_create=UserCreate(email="qa_teacher@example.com", password="teacher123456"),
            )
        if user.is_superuser:
            pytest.skip("该账号为超管，不适用无权限断言")
        assert get_user_permissions(db, user) == set()
        assert user_has_permission(db, user, PERM_REVIEW) is False

    def test_org_chain_no_cycle(self, db):
        """⚠️ 边界：组织链对不存在的 org 应安全终止（不无限循环）"""
        from app.core.rbac import org_chain

        chain = org_chain(db, "00000000-0000-0000-0000-000000000000")
        assert isinstance(chain, list)
        assert len(chain) <= 1  # 不存在则最多返回自身
