"""一键灌库脚本入口。

预置示范知识库（初中物理 人教版八上）的「一键灌库脚本」。
在 backend 目录下运行：

    python -m scripts.seed_demo

脚本会幂等地：
- 创建演示账号 teacher@example.com / admin@example.com
- 写入 Neo4j 示范知识图谱（知识点 + 前置/包含关系 + 考点 + 误区）
- 写入 PostgreSQL 学科 / 教材 / 章节树 / 教材切片文档（供 RAG）

编排逻辑见 backend/app/initial_data.py::seed_knowledge_graph
（与「上传教材 → extraction_graph 自动抽取」共享 find_by_name 全局去重）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.initial_data import seed_knowledge_graph  # noqa: E402

if __name__ == "__main__":
    seed_knowledge_graph()
