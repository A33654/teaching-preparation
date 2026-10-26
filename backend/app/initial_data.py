from __future__ import annotations

import logging
import uuid

from sqlmodel import Session

from app.core.db import engine, init_db
from app.seed_demo import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DEMO_DATA,
    TEACHER_EMAIL,
    TEACHER_PASSWORD,
    _create_chapter,
    _ensure_document,
    _ensure_exam,
    _ensure_kp,
    _ensure_mis,
    _ensure_subject,
    _ensure_textbook,
    _ensure_user,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    with Session(engine) as session:
        init_db(session)


# ---------------------------------------------------------------------------
# 演示知识库灌库（手工 + LLM 辅助编纂的种子，人工核验后批量写入 Neo4j）
# ---------------------------------------------------------------------------


def seed_knowledge_graph() -> None:
    """预置示范知识库（幂等），调用 KnowledgeGraphRepository 批量建节点/关系。

    种子数据见 app/seed_demo.DEMO_DATA（初中物理 人教版八年级上册，约 34 个知识点，
    每个节点带 定义 / 难度(1-5) / 是否核心考点 / 前置关系(prerequisite) /
    考纲考点(了解·理解·掌握) / 学生误区+纠正）。同时创建演示账号。

    与「上传教材 → extraction_graph 自动抽取」路径共享同一套去重逻辑：
    KnowledgeGraphRepository.find_by_name 按名全局查重，故两条路径的结果可合并、不重复。

    幂等：若示范图谱根节点已存在则跳过；关系 / 考点 / 误区 / 学科 / 教材 / 文档均按存在性跳过。
    """
    from app.knowledge_graph import KnowledgeGraphRepository

    repo = KnowledgeGraphRepository()

    # 幂等守卫：示范图谱已存在则直接返回（如需重置请先清空 Neo4j 与数据库）
    if repo.find_by_name("光的反射", None):
        logger.info("示范知识库已存在，跳过灌库（如需重置请先清空 Neo4j 与数据库）")
        return

    teacher = _ensure_user(
        TEACHER_EMAIL, TEACHER_PASSWORD, is_superuser=False, full_name="演示教师"
    )
    _ensure_user(ADMIN_EMAIL, ADMIN_PASSWORD, is_superuser=True, full_name="演示管理员")
    teacher_id = str(teacher.id)

    kp_name_to_id: dict[str, str] = {}  # 全局 name -> neo4j id（关系解析用）

    for subj_data in DEMO_DATA:
        subject = _ensure_subject(teacher.id, subj_data["name"], subj_data["grade"])
        textbook = _ensure_textbook(teacher.id, subject.id, subj_data["textbook"])

        # 1) 知识点（先于章节，便于章节挂载 knowledge_point_id）
        for kp_name, spec in subj_data["knowledge_points"].items():
            kp_id = _ensure_kp(
                repo, teacher_id, kp_name, subj_data["name"], subj_data["grade"], spec
            )
            kp_name_to_id[kp_name] = kp_id
            for exam in spec.get("exam", []):
                _ensure_exam(repo, teacher_id, kp_id, exam)
            for mis in spec.get("mis", []):
                _ensure_mis(repo, teacher_id, kp_id, mis)

        # 2) 关系（prerequisite / contains …）
        for src_name, dst_name, rel_type in subj_data["relations"]:
            src = kp_name_to_id.get(src_name)
            dst = kp_name_to_id.get(dst_name)
            if src and dst:
                try:
                    repo.create_relation(src, dst, rel_type)
                except Exception as e:  # 关系已存在等，忽略
                    logger.debug(
                        "关系跳过 %s->%s (%s): %s", src_name, dst_name, rel_type, e
                    )

        # 3) 章节树（按名称解析 knowledge_point_id）
        def _build(nodes: list[dict], parent_id: uuid.UUID | None, order: int = 0):
            for i, node in enumerate(nodes):
                kp_name = node.get("kp")
                kp_id = kp_name_to_id.get(kp_name) if kp_name else None
                ch = _create_chapter(
                    teacher.id, textbook.id, node["title"], node["level"],
                    order + i, parent_id, kp_id,
                )
                if node.get("children"):
                    _build(node["children"], ch.id)

        _build(subj_data["chapters"], None)

        # 4) 教材切片文档 + Neo4j MENTIONS 关系（供 lesson_plan 的 RAG 检索）
        for doc in subj_data["documents"]:
            kp_ids = [kp_name_to_id[n] for n in doc["kp"] if n in kp_name_to_id]
            d = _ensure_document(teacher.id, subject.id, doc["title"], doc["text"], kp_ids)
            try:
                repo.link_document_knowledge_points(str(d.id), kp_ids)
            except Exception as e:
                logger.debug("文档-知识点关联跳过: %s", e)

    logger.info(
        "示范知识库灌库完成：%d 个学科，Neo4j 知识点已写入；演示账号 %s / %s",
        len(DEMO_DATA),
        TEACHER_EMAIL,
        ADMIN_EMAIL,
    )


def main() -> None:
    logger.info("Creating initial data")
    init()
    # 演示库灌库：best-effort，Neo4j 未就绪时跳过（后端 on_startup 还会再尝试），不阻断启动
    try:
        seed_knowledge_graph()
    except Exception as e:  # noqa: BLE001
        logger.warning("演示库自动灌库跳过（Neo4j/数据库未就绪）：%s", e)
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
