# -*- coding: utf-8 -*-
"""L0 单元测试：Pydantic/SQLModel 入参校验（空白值 / 错误 / 边界）。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestUserCreateValidation:
    def test_valid_user(self):
        """✅ 正常：合法邮箱与密码"""
        from app.models import UserCreate

        u = UserCreate(email="valid@example.com", password="password123")
        assert u.email == "valid@example.com"

    def test_invalid_email_rejected(self):
        """❌ 错误：非法邮箱格式应被拒绝"""
        from app.models import UserCreate

        with pytest.raises(ValidationError):
            UserCreate(email="not-an-email", password="password123")

    def test_empty_email_rejected(self):
        """🈳 空白值：空邮箱应被拒绝"""
        from app.models import UserCreate

        with pytest.raises(ValidationError):
            UserCreate(email="", password="password123")

    def test_missing_password_rejected(self):
        """🈳 空白值：缺失必填密码应被拒绝"""
        from app.models import UserCreate

        with pytest.raises(ValidationError):
            UserCreate(email="someone@example.com")  # type: ignore[call-arg]


class TestLessonPlanValidation:
    """教案标题/学科的 min_length=1 / max_length 边界。"""

    def test_valid_lesson_plan(self):
        """✅ 正常"""
        from app.models import LessonPlanCreate

        lp = LessonPlanCreate(title="光的反射", subject="物理")
        assert lp.title == "光的反射"

    def test_empty_title_rejected(self):
        """🈳 空白值：空标题违反 min_length=1"""
        from app.models import LessonPlanCreate

        with pytest.raises(ValidationError):
            LessonPlanCreate(title="", subject="物理")

    def test_empty_subject_rejected(self):
        """🈳 空白值：空学科应被拒绝"""
        from app.models import LessonPlanCreate

        with pytest.raises(ValidationError):
            LessonPlanCreate(title="光的反射", subject="")

    def test_title_max_length_boundary(self):
        """⚠️ 边界：标题 255 字符通过、256 字符被拒"""
        from app.models import LessonPlanCreate

        ok = LessonPlanCreate(title="a" * 255, subject="物理")
        assert len(ok.title) == 255
        with pytest.raises(ValidationError):
            LessonPlanCreate(title="a" * 256, subject="物理")

    def test_subject_max_length_boundary(self):
        """⚠️ 边界：学科 100 字符通过、101 字符被拒"""
        from app.models import LessonPlanCreate

        ok = LessonPlanCreate(title="光的反射", subject="物" * 100)
        assert len(ok.subject) == 100
        with pytest.raises(ValidationError):
            LessonPlanCreate(title="光的反射", subject="物" * 101)

    def test_missing_required_fields(self):
        """🈳 空白值：完全空负载应被拒绝"""
        from app.models import LessonPlanCreate

        with pytest.raises(ValidationError):
            LessonPlanCreate()  # type: ignore[call-arg]
