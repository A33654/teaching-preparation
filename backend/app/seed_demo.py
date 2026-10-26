"""一键灌库脚本 —— 预置示范知识库（初中物理 人教版八上）。

作用：
- 解决「库空 → 教师一进来全是『知识库未收录 → RAG 兜底』，图谱差异化卖点失效」的问题。
- 预置**初中物理（人教版八年级上册）**示范知识图谱（Neo4j，约 34 个知识点）+ 教材切片
  （PostgreSQL 文档，供 RAG），教师登录即可看到「知识库完整（图谱驱动）」。
- 知识点前置链清晰：光源 → 光的直线传播 → 光的反射 → 光的折射 → 透镜 → 凸透镜成像规律
  → 眼睛和眼镜，最能体现知识图谱的「结构化知识骨架 + 逻辑约束」价值。
- 同时创建演示账号（teacher@example.com / admin@example.com），保证 demo 开箱即用。

幂等：重复执行安全（知识点按名全局去重，关系/考点/误区按存在性跳过，
学科/教材/文档按名跳过，整库已灌过则直接返回）。

本模块只负责**种子数据与幂等辅助函数**；真正的灌库编排在 app/initial_data.seed_knowledge_graph
（在 prestart / 后端启动时自动调用，也与「上传教材 → extraction_graph 自动抽取」共享
KnowledgeGraphRepository.find_by_name 的全局去重，两条路径结果可合并、不重复）。

用法：
- 一键灌库脚本（推荐，最直观）：
      cd backend && python -m scripts.seed_demo
- 在代码中调用（两种入口等价）：
      from app.initial_data import seed_knowledge_graph
      seed_knowledge_graph()
  # 或兼容旧调用：from app.seed_demo import run_seed_demo; run_seed_demo()
- 应用启动时若 settings.SEED_DEMO_ON_STARTUP=True 且图谱为空，会自动灌库
  （见 app/main.py 的 on_startup → app/initial_data.seed_knowledge_graph）。

依赖：PostgreSQL 与 Neo4j 均已就绪（先完成 alembic 迁移 / docker compose 启动）。
"""
from __future__ import annotations

import logging
import uuid

from sqlmodel import Session, select

from app.core.db import engine
from app.core.security import get_password_hash
from app.models import (
    Chapter,
    Document,
    DocumentStatus,
    Subject,
    Textbook,
    User,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 演示账号（教师端 / 管理员端）
# ---------------------------------------------------------------------------
TEACHER_EMAIL = "teacher@example.com"
TEACHER_PASSWORD = "teacher123456"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123456"


# ---------------------------------------------------------------------------
# 示范知识库数据：初中物理（人教版八年级上册）
# 设计原则：
# - hero 前置链：光源 → 光的直线传播 → 光的反射 → 光的折射 → 透镜 →
#   凸透镜成像规律 → 眼睛和眼镜（跨章节：第四章光现象 → 第五章透镜及其应用），
#   体现图谱对「知识依赖关系」的结构化表达，是最大差异化卖点。
# - 每个 hero 章节（光的反射 / 光的折射 / 透镜 / 凸透镜成像规律）在 Neo4j 拥有
#   多个「核心考点」知识点且名称/描述含章节关键词，保证章节检索命中 >=3，
#   从而 coverage=complete（图谱驱动，而非 RAG 兜底）。
# - 教材切片文档的 extracted_text 内含章节与知识点关键词，供 lesson_plan 图做 RAG 检索。
# ---------------------------------------------------------------------------

DEMO_DATA: list[dict] = [
    {
        "name": "初中物理",
        "grade": "初中",
        "textbook": {
            "name": "人教版 初中物理 八年级上册",
            "version": "人教版",
            "description": "初中物理八年级上册示范教材（机械运动/声现象/物态变化/光现象/透镜/质量与密度）",
        },
        "chapters": [
            {
                "title": "人教版 初中物理 八年级上册",
                "level": 0,
                "kp": None,
                "children": [
                    {
                        "title": "第一章 机械运动",
                        "level": 1,
                        "kp": None,
                        "children": [
                            {"title": "1.1 长度和时间的测量", "level": 2, "kp": "长度的单位与测量"},
                            {"title": "1.2 运动的描述", "level": 2, "kp": "机械运动"},
                            {"title": "1.3 运动的快慢", "level": 2, "kp": "速度"},
                            {"title": "1.4 测量平均速度", "level": 2, "kp": "测量平均速度"},
                        ],
                    },
                    {
                        "title": "第二章 声现象",
                        "level": 1,
                        "kp": "声音的产生",
                        "children": [
                            {"title": "2.1 声音的产生与传播", "level": 2, "kp": "声音的传播"},
                            {"title": "2.2 声音的特性", "level": 2, "kp": "音调"},
                            {"title": "2.3 声的利用", "level": 2, "kp": "声的利用"},
                        ],
                    },
                    {
                        "title": "第三章 物态变化",
                        "level": 1,
                        "kp": "温度",
                        "children": [
                            {"title": "3.1 温度", "level": 2, "kp": "温度"},
                            {"title": "3.2 熔化和凝固", "level": 2, "kp": "熔化"},
                            {"title": "3.3 汽化和液化", "level": 2, "kp": "汽化"},
                            {"title": "3.4 升华和凝华", "level": 2, "kp": "升华"},
                        ],
                    },
                    {
                        "title": "第四章 光现象",
                        "level": 1,
                        "kp": "光的反射",
                        "children": [
                            {"title": "4.1 光的直线传播", "level": 2, "kp": "光的直线传播"},
                            {"title": "4.2 光的反射", "level": 2, "kp": "光的反射"},
                            {"title": "4.3 平面镜成像", "level": 2, "kp": "平面镜成像"},
                            {"title": "4.4 光的折射", "level": 2, "kp": "光的折射"},
                            {"title": "4.5 光的色散", "level": 2, "kp": "光的色散"},
                        ],
                    },
                    {
                        "title": "第五章 透镜及其应用",
                        "level": 1,
                        "kp": "透镜",
                        "children": [
                            {"title": "5.1 透镜", "level": 2, "kp": "透镜"},
                            {"title": "5.2 生活中的透镜", "level": 2, "kp": "凸透镜"},
                            {"title": "5.3 凸透镜成像规律", "level": 2, "kp": "凸透镜成像规律"},
                            {"title": "5.4 眼睛和眼镜", "level": 2, "kp": "眼睛和眼镜"},
                            {"title": "5.5 显微镜和望远镜", "level": 2, "kp": "显微镜"},
                        ],
                    },
                    {
                        "title": "第六章 质量与密度",
                        "level": 1,
                        "kp": "质量",
                        "children": [
                            {"title": "6.1 质量", "level": 2, "kp": "质量"},
                            {"title": "6.2 密度", "level": 2, "kp": "密度"},
                            {"title": "6.3 测量物质的密度", "level": 2, "kp": "密度的测量"},
                            {"title": "6.4 密度与社会生活", "level": 2, "kp": "密度与社会生活"},
                        ],
                    },
                ],
            }
        ],
        "knowledge_points": {
            # ---------------- 第一章 机械运动 ----------------
            "长度的单位与测量": {
                "desc": "长度的基本单位是米（m），常用单位有千米、分米、厘米、毫米等。测量长度常用的工具是刻度尺，"
                "读数时要估读到分度值的下一位。长度的单位换算是初中物理最基本的测量技能。",
                "key": True,
                "difficulty": 2,
                "exam": [
                    {"name": "长度单位之间的换算", "level": "了解"},
                    {"name": "用刻度尺正确测量并读数", "level": "理解"},
                ],
                "mis": [
                    {
                        "content": "读数时没有估读到分度值的下一位",
                        "correction": "用刻度尺测量时，读数要估读到分度值的下一位。",
                    },
                    {
                        "content": "混淆分度值与测量值",
                        "correction": "分度值是尺子能准确读出的最小格值，测量值包含准确值加估读值。",
                    },
                ],
            },
            "机械运动": {
                "desc": "物体位置的变化叫做机械运动。判断物体运动还是静止，要看所选的参照物；"
                "运动和静止是相对的。机械运动是自然界中最常见的运动形式。",
                "key": True,
                "difficulty": 2,
                "exam": [{"name": "用参照物描述物体的运动或静止", "level": "理解"}],
                "mis": [
                    {
                        "content": "认为静止是绝对的",
                        "correction": "运动和静止是相对的，取决于所选的参照物。",
                    }
                ],
            },
            "速度": {
                "desc": "速度是表示物体运动快慢的物理量，等于路程与时间的比值 v=s/t。速度的单位有 m/s 和 km/h，"
                "1 m/s = 3.6 km/h。速度初中物理运动学的核心公式。",
                "key": True,
                "difficulty": 4,
                "exam": [
                    {"name": "理解速度的物理意义", "level": "理解"},
                    {"name": "用速度公式进行简单计算", "level": "掌握"},
                ],
                "mis": [
                    {
                        "content": "混淆速度与速率、把平均速度当瞬时速度",
                        "correction": "速度是矢量，运动学计算先统一单位再代入公式 v=s/t。",
                    },
                    {
                        "content": "单位未统一就直接代入公式",
                        "correction": "计算前确保 s、t 单位对应（如 m 与 s 对应 m/s）。",
                    },
                ],
            },
            "匀速直线运动": {
                "desc": "物体沿直线且速度不变的运动叫匀速直线运动，其 s-t 图象是一条过原点的倾斜直线，"
                "v-t 图象是一条平行于时间轴的直线。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "识别匀速直线运动的图象", "level": "理解"}],
                "mis": [],
            },
            "测量平均速度": {
                "desc": "用刻度尺测路程、停表测时间，利用 v=s/t 计算物体在某段路程的平均速度。"
                "实验是初中物理重要的测量型实验。",
                "key": False,
                "difficulty": 3,
                "exam": [{"name": "用停表测量时间并计算平均速度", "level": "理解"}],
                "mis": [
                    {
                        "content": "用路程除以总时间当作某段的平均速度",
                        "correction": "平均速度要用『该段的路程』除以『该段的时间』，不能混用总时间。",
                    }
                ],
            },
            # ---------------- 第二章 声现象 ----------------
            "声音的产生": {
                "desc": "声音是由物体振动产生的，一切发声的物体都在振动；振动停止，发声也停止。"
                "声音的产生与传播是声学的基础。",
                "key": True,
                "difficulty": 2,
                "exam": [{"name": "举例说明声音由物体的振动产生", "level": "理解"}],
                "mis": [
                    {
                        "content": "认为不振动也能发声",
                        "correction": "声音是由物体振动产生的，没有振动就没有声音。",
                    }
                ],
            },
            "声音的传播": {
                "desc": "声音的传播需要介质，固体、液体、气体都能传声，真空不能传声。声音是一种波。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "声音传播需要介质，真空不能传声", "level": "理解"}],
                "mis": [
                    {
                        "content": "认为真空也能传声",
                        "correction": "真空不能传声，太空中无法直接对话。",
                    }
                ],
            },
            "声速": {
                "desc": "声速是声音传播的快慢。15℃ 空气中声速约 340 m/s，一般情况下 "
                "v固体 > v液体 > v气体。声音的产生与传播都离不开介质。",
                "key": False,
                "difficulty": 2,
                "exam": [{"name": "比较不同介质中的声速", "level": "了解"}],
                "mis": [],
            },
            "音调": {
                "desc": "音调指声音的高低，由发声体振动的频率决定，频率越高音调越高。"
                "声音的特性包括音调、响度和音色。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "理解音调与频率的关系", "level": "理解"}],
                "mis": [
                    {
                        "content": "混淆音调与响度",
                        "correction": "音调由频率决定（高低），响度由振幅决定（大小），二者不同。",
                    }
                ],
            },
            "响度": {
                "desc": "响度指声音的强弱，由发声体振动的振幅决定，振幅越大响度越大；"
                "距离发声体越远响度越小。",
                "key": False,
                "difficulty": 2,
                "exam": [{"name": "理解响度与振幅的关系", "level": "理解"}],
                "mis": [],
            },
            "声的利用": {
                "desc": "声音可以传递信息（如 B 超、声呐），也可以传递能量（如超声波清洗、碎石）。",
                "key": False,
                "difficulty": 2,
                "exam": [{"name": "举例说明声能传递信息和能量", "level": "了解"}],
                "mis": [],
            },
            # ---------------- 第三章 物态变化 ----------------
            "温度": {
                "desc": "温度表示物体的冷热程度。常用温度计是根据液体热胀冷缩的规律制成的，"
                "摄氏温度把冰水混合物的温度规定为 0℃，沸水的温度规定为 100℃。",
                "key": True,
                "difficulty": 2,
                "exam": [{"name": "理解温度的物理意义", "level": "理解"}],
                "mis": [
                    {
                        "content": "把温度和温度计混为一谈",
                        "correction": "温度是物体的冷热程度，温度计是测量温度的工具。",
                    }
                ],
            },
            "熔化": {
                "desc": "物质由固态变成液态叫熔化。晶体有固定熔点，熔化时吸热温度不变；"
                "非晶体没有固定熔点。熔化和凝固是物态变化的重要类型。",
                "key": True,
                "difficulty": 3,
                "exam": [
                    {"name": "区分晶体与非晶体", "level": "掌握"},
                    {"name": "理解晶体熔化的特点", "level": "理解"},
                ],
                "mis": [
                    {
                        "content": "认为熔化都要吸热且温度不变",
                        "correction": "只有晶体熔化时温度保持不变，非晶体熔化时温度持续上升。",
                    }
                ],
            },
            "凝固": {
                "desc": "物质由液态变成固态叫凝固。晶体凝固时有固定凝固点，凝固时放热温度不变。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "理解凝固的特点", "level": "理解"}],
                "mis": [],
            },
            "汽化": {
                "desc": "物质由液态变成气态叫汽化，汽化吸热。汽化有蒸发和沸腾两种方式："
                "蒸发在任何温度都能发生，沸腾要达到沸点并持续吸热。",
                "key": True,
                "difficulty": 3,
                "exam": [
                    {"name": "区分蒸发和沸腾", "level": "理解"},
                    {"name": "了解沸点与气压的关系", "level": "了解"},
                ],
                "mis": [
                    {
                        "content": "认为沸腾时温度持续升高",
                        "correction": "水沸腾时吸热但温度保持不变（等于沸点）。",
                    }
                ],
            },
            "液化": {
                "desc": "物质由气态变成液态叫液化，液化放热。使气体液化的方法有降低温度和压缩体积。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "举例说明生活中的液化现象", "level": "理解"}],
                "mis": [
                    {
                        "content": "混淆汽化与液化",
                        "correction": "汽化是液→气，液化是气→液，二者方向相反。",
                    }
                ],
            },
            "升华": {
                "desc": "物质由固态直接变成气态叫升华，升华吸热（如樟脑丸变小、冰冻衣服变干）。",
                "key": False,
                "difficulty": 2,
                "exam": [{"name": "举例说明升华现象", "level": "了解"}],
                "mis": [
                    {
                        "content": "把升华当成熔化",
                        "correction": "升华是固态直接变气态，中间不经过液态。",
                    }
                ],
            },
            # ---------------- 第四章 光现象（hero 前置链起点） ----------------
            "光源": {
                "desc": "自身能够发光的物体叫光源，分为天然光源（如太阳）和人造光源（如电灯）。"
                "月亮不是光源，它反射太阳光。",
                "key": False,
                "difficulty": 1,
                "exam": [{"name": "识别天然光源和人造光源", "level": "了解"}],
                "mis": [
                    {
                        "content": "认为月亮是光源",
                        "correction": "月亮本身不发光，它是反射太阳光，所以不是光源。",
                    }
                ],
            },
            "光的直线传播": {
                "desc": "光在同种均匀介质中沿直线传播。小孔成像、影子的形成、日食月食都是光的直线传播的例证。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "用光的直线传播解释影子、日食等现象", "level": "理解"}],
                "mis": [
                    {
                        "content": "认为光总是沿直线传播",
                        "correction": "光只有在同种均匀介质中才沿直线传播，遇到不同介质或不均匀介质会偏折。",
                    }
                ],
            },
            "光的反射": {
                "desc": "光遇到水面、镜面等物体表面返回原来介质的现象叫光的反射，遵循光的反射定律。"
                "光的反射是初中物理光学部分的核心内容，平面镜成像即由光的反射形成。",
                "key": True,
                "difficulty": 4,
                "exam": [{"name": "理解光的反射现象", "level": "理解"}],
                "mis": [
                    {
                        "content": "把反射光线与入射光线弄反",
                        "correction": "反射光线和入射光线分居法线两侧，反射角始终等于入射角。",
                    }
                ],
            },
            "光的反射定律": {
                "desc": "光的反射定律：反射光线、入射光线和法线在同一平面内；反射光线和入射光线"
                "分居法线两侧；反射角等于入射角。是初中物理光现象的重点规律。",
                "key": True,
                "difficulty": 4,
                "exam": [{"name": "用光的反射定律作图与解释现象", "level": "掌握"}],
                "mis": [
                    {
                        "content": "混淆入射角与反射角的定义，误以为是和镜面的夹角",
                        "correction": "入射角、反射角都是与法线（垂直镜面的虚线）的夹角。",
                    }
                ],
            },
            "平面镜成像": {
                "desc": "平面镜成像由光的反射形成，像与物关于镜面对称：等大、等距、虚像。"
                "是初中物理光现象的重要应用。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "探究并描述平面镜成像的特点", "level": "理解"}],
                "mis": [
                    {
                        "content": "认为平面镜成的是实像",
                        "correction": "平面镜成的是虚像，不能用光屏承接。",
                    }
                ],
            },
            "光的折射": {
                "desc": "光从一种介质斜射入另一种介质时，传播方向发生偏折的现象叫光的折射。"
                "光的折射是透镜成像的基础，与光的反射共同构成几何光学核心。",
                "key": True,
                "difficulty": 4,
                "exam": [{"name": "用光的折射规律解释现象", "level": "理解"}],
                "mis": [
                    {
                        "content": "混淆折射角与反射角，误以为折射角一定小于入射角",
                        "correction": "折射角是折射光线与法线的夹角；从空气斜射入水/玻璃时折射角小于入射角，反之则大于。",
                    }
                ],
            },
            "光的色散": {
                "desc": "太阳光（白光）通过三棱镜后会分解成红、橙、黄、绿、蓝、靛、紫七种色光，"
                "说明白光是由各种色光混合而成的。光的色散本质上是光在不同介质中发生光的折射时"
                "偏折程度不同造成的。",
                "key": True,
                "difficulty": 2,
                "exam": [{"name": "知道白光由多种色光组成", "level": "了解"}],
                "mis": [],
            },
            # ---------------- 第五章 透镜及其应用（hero 前置链终点） ----------------
            "透镜": {
                "desc": "透镜是利用光的折射规律工作的光学元件。中间厚边缘薄的叫凸透镜（对光线有会聚作用），"
                "中间薄边缘厚的叫凹透镜（对光线有发散作用）。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "区分凸透镜和凹透镜及其对光线的作用", "level": "理解"}],
                "mis": [
                    {
                        "content": "混淆凸透镜与凹透镜对光线的作用",
                        "correction": "凸透镜对光线有会聚作用，凹透镜对光线有发散作用。",
                    }
                ],
            },
            "凸透镜": {
                "desc": "凸透镜中间厚、边缘薄，对光线有会聚作用。平行于主光轴的光经凸透镜折射后"
                "会聚于一点，该点叫焦点，焦点到光心的距离叫焦距。",
                "key": False,
                "difficulty": 2,
                "exam": [{"name": "认识凸透镜的焦点和焦距", "level": "了解"}],
                "mis": [],
            },
            "凹透镜": {
                "desc": "凹透镜中间薄、边缘厚，对光线有发散作用。平行于主光轴的光经凹透镜折射后"
                "发散，其反向延长线交于虚焦点。",
                "key": False,
                "difficulty": 2,
                "exam": [{"name": "认识凹透镜", "level": "了解"}],
                "mis": [],
            },
            "凸透镜成像规律": {
                "desc": "凸透镜成像规律：物距 u>2f 成倒立缩小实像（照相机）；f<u<2f 成倒立放大实像"
                "（投影仪）；u<f 成正立放大虚像（放大镜）。一倍焦距分虚实，二倍焦距分大小。",
                "key": True,
                "difficulty": 5,
                "exam": [
                    {"name": "探究并掌握凸透镜成像规律", "level": "掌握"},
                    {"name": "用成像规律解释生活中的应用", "level": "理解"},
                ],
                "mis": [
                    {
                        "content": "记错成实像与虚像、放大与缩小的分界",
                        "correction": "一倍焦距分虚实（u=f 不成像），二倍焦距分大小。",
                    },
                    {
                        "content": "把实像虚像与正倒混为一谈",
                        "correction": "实像都是倒立的，虚像都是正立的；与放大缩小无关。",
                    },
                ],
            },
            "眼睛和眼镜": {
                "desc": "眼睛的晶状体相当于凸透镜，视网膜相当于光屏，其成像原理建立在凸透镜成像规律之上。"
                "近视眼成像在视网膜前，需配戴凹透镜矫正；远视眼成像在视网膜后，需配戴凸透镜矫正。",
                "key": True,
                "difficulty": 3,
                "exam": [{"name": "理解近视眼、远视眼的成因与矫正", "level": "理解"}],
                "mis": [
                    {
                        "content": "混淆近视与远视的矫正透镜",
                        "correction": "近视眼用凹透镜矫正，远视眼用凸透镜矫正。",
                    }
                ],
            },
            "显微镜": {
                "desc": "显微镜的物镜成倒立放大实像，目镜成正立放大虚像，两次放大可观察微小物体，"
                "其原理建立在凸透镜成像规律之上。",
                "key": True,
                "difficulty": 2,
                "exam": [{"name": "了解显微镜的光学原理", "level": "了解"}],
                "mis": [],
            },
            # ---------------- 第六章 质量与密度 ----------------
            "质量": {
                "desc": "物体所含物质的多少叫质量，基本单位是千克（kg）。质量是物体的固有属性，"
                "不随物体的形状、状态、位置而改变。",
                "key": True,
                "difficulty": 2,
                "exam": [{"name": "理解质量的概念", "level": "理解"}],
                "mis": [
                    {
                        "content": "认为质量随位置或状态变化",
                        "correction": "质量是物体本身的一种属性，与位置、状态无关。",
                    }
                ],
            },
            "密度": {
                "desc": "某种物质组成的物体的质量与体积之比叫这种物质的密度，公式 ρ=m/V。"
                "密度是物质的一种特性，与质量和体积无关。",
                "key": True,
                "difficulty": 4,
                "exam": [
                    {"name": "理解密度的概念并进行简单计算", "level": "掌握"},
                    {"name": "识别密度是物质的特性", "level": "理解"},
                ],
                "mis": [
                    {
                        "content": "认为密度随质量或体积变化",
                        "correction": "密度是物质的特性，对同一物质在相同状态下密度不变。",
                    }
                ],
            },
            "密度的测量": {
                "desc": "用天平测质量、量筒（量杯）测体积，利用 ρ=m/V 计算物质密度。"
                "量筒读数时视线要与液面凹面最低处相平。",
                "key": True,
                "difficulty": 4,
                "exam": [{"name": "用天平和量筒测量固体、液体的密度", "level": "掌握"}],
                "mis": [
                    {
                        "content": "量筒读数时俯视或仰视",
                        "correction": "读数时视线应与量筒内液体凹液面的最低处保持相平。",
                    }
                ],
            },
            "密度与社会生活": {
                "desc": "密度在生活中有广泛应用：鉴别物质、判断物体空心实心、计算不便直接测量的质量或体积。",
                "key": False,
                "difficulty": 2,
                "exam": [{"name": "用密度知识鉴别物质", "level": "了解"}],
                "mis": [],
            },
        },
        "relations": [
            # 机械运动
            ["机械运动", "长度的单位与测量", "prerequisite"],
            ["速度", "机械运动", "prerequisite"],
            ["速度", "长度的单位与测量", "prerequisite"],
            ["匀速直线运动", "速度", "prerequisite"],
            ["测量平均速度", "速度", "prerequisite"],
            # 声现象
            ["声音的传播", "声音的产生", "prerequisite"],
            ["声速", "声音的传播", "prerequisite"],
            ["音调", "声音的产生", "prerequisite"],
            ["响度", "声音的产生", "prerequisite"],
            ["声的利用", "声音的传播", "prerequisite"],
            # 物态变化
            ["熔化", "温度", "prerequisite"],
            ["凝固", "熔化", "prerequisite"],
            ["汽化", "温度", "prerequisite"],
            ["液化", "汽化", "prerequisite"],
            ["升华", "熔化", "prerequisite"],
            # 光现象（hero 前置链）
            ["光的直线传播", "光源", "prerequisite"],
            ["光的反射", "光的直线传播", "prerequisite"],
            ["光的反射定律", "光的反射", "prerequisite"],
            ["平面镜成像", "光的反射", "prerequisite"],
            ["光的折射", "光的反射", "prerequisite"],
            ["光的色散", "光的折射", "prerequisite"],
            # 透镜及其应用（hero 前置链延续）
            ["透镜", "光的折射", "prerequisite"],
            ["凸透镜", "透镜", "prerequisite"],
            ["凹透镜", "透镜", "prerequisite"],
            ["凸透镜成像规律", "透镜", "prerequisite"],
            ["眼睛和眼镜", "凸透镜成像规律", "prerequisite"],
            ["显微镜", "凸透镜成像规律", "prerequisite"],
            # 质量与密度
            ["密度", "质量", "prerequisite"],
            ["密度的测量", "密度", "prerequisite"],
            ["密度与社会生活", "密度", "prerequisite"],
        ],
        "documents": [
            {
                "title": "人教版八年级上册·第四章 光现象（教材切片）",
                "text": (
                    "第四章 光现象\n\n"
                    "4.1 光的直线传播\n"
                    "光在同种均匀介质中沿直线传播。小孔成像、影子、日食和月食都是光的直线传播的例证。\n\n"
                    "4.2 光的反射\n"
                    "光遇到水面、墙面以及其他许多物体的表面都会发生反射。光的反射遵循光的反射定律："
                    "反射光线、入射光线和法线在同一平面内；反射光线和入射光线分居法线两侧；"
                    "反射角等于入射角。入射角、反射角都是与法线的夹角。\n\n"
                    "4.3 平面镜成像\n"
                    "平面镜成像是由光的反射形成的。平面镜所成的像与物体关于镜面对称：像与物体大小"
                    "相等，像到平面镜的距离等于物体到平面镜的距离，像是虚像。\n\n"
                    "4.4 光的折射\n"
                    "光从一种介质斜射入另一种介质时，传播方向发生偏折，这种现象叫光的折射。光的折射"
                    "是透镜成像的基础。\n\n"
                    "4.5 光的色散\n"
                    "太阳光通过三棱镜后分解成红、橙、黄、绿、蓝、靛、紫七种色光，说明白光是由各种"
                    "色光混合而成的。"
                ),
                "kp": [
                    "光源",
                    "光的直线传播",
                    "光的反射",
                    "光的反射定律",
                    "平面镜成像",
                    "光的折射",
                    "光的色散",
                ],
            },
            {
                "title": "人教版八年级上册·第五章 透镜及其应用（教材切片）",
                "text": (
                    "第五章 透镜及其应用\n\n"
                    "5.1 透镜\n"
                    "透镜是利用光的折射规律工作的光学元件。中间厚边缘薄的叫凸透镜，对光线有会聚作用；"
                    "中间薄边缘厚的叫凹透镜，对光线有发散作用。\n\n"
                    "5.3 凸透镜成像规律\n"
                    "凸透镜成像：物距大于二倍焦距成倒立缩小实像（照相机原理）；物距在一倍到二倍焦距"
                    "之间成倒立放大实像（投影仪原理）；物距小于焦距成正立放大虚像（放大镜原理）。"
                    "一倍焦距分虚实，二倍焦距分大小。\n\n"
                    "5.4 眼睛和眼镜\n"
                    "眼睛的晶状体相当于凸透镜。近视眼成像在视网膜前，配戴凹透镜矫正；远视眼成像在"
                    "视网膜后，配戴凸透镜矫正。\n\n"
                    "5.5 显微镜和望远镜\n"
                    "显微镜通过物镜和目镜两次放大观察微小物体，其原理都建立在凸透镜成像规律之上。"
                ),
                "kp": [
                    "透镜",
                    "凸透镜",
                    "凹透镜",
                    "凸透镜成像规律",
                    "眼睛和眼镜",
                    "显微镜",
                ],
            },
            {
                "title": "人教版八年级上册·第二章 声现象（教材切片）",
                "text": (
                    "第二章 声现象\n\n"
                    "2.1 声音的产生与传播\n"
                    "声音是由物体的振动产生的。声音的传播需要介质，固体、液体、气体都可以传声，"
                    "真空不能传声。15℃ 时空气中的声速约为 340 m/s。\n\n"
                    "2.2 声音的特性\n"
                    "音调指声音的高低，由频率决定；响度指声音的强弱，由振幅决定；音色由发声体本身"
                    "的材料和结构决定。\n\n"
                    "2.3 声的利用\n"
                    "声音可以传递信息，也可以传递能量。"
                ),
                "kp": [
                    "声音的产生",
                    "声音的传播",
                    "声速",
                    "音调",
                    "响度",
                    "声的利用",
                ],
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# 辅助函数（均幂等）
# ---------------------------------------------------------------------------


def _ensure_user(email: str, password: str, *, is_superuser: bool, full_name: str) -> User:
    with Session(engine) as s:
        existing = s.exec(select(User).where(User.email == email)).first()
        if existing:
            return existing
        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_superuser=is_superuser,
            full_name=full_name,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        logger.info("创建演示账号: %s", email)
        return user


def _ensure_subject(owner_id: uuid.UUID, name: str, grade: str) -> Subject:
    with Session(engine) as s:
        existing = s.exec(
            select(Subject).where(Subject.name == name, Subject.owner_id == owner_id)
        ).first()
        if existing:
            return existing
        subj = Subject(name=name, owner_id=owner_id, description=f"{grade}示范学科")
        s.add(subj)
        s.commit()
        s.refresh(subj)
        return subj


def _ensure_textbook(owner_id: uuid.UUID, subject_id: uuid.UUID, tb: dict) -> Textbook:
    with Session(engine) as s:
        existing = s.exec(
            select(Textbook).where(Textbook.name == tb["name"], Textbook.owner_id == owner_id)
        ).first()
        if existing:
            return existing
        textbook = Textbook(
            name=tb["name"],
            version=tb.get("version"),
            grade_level=tb.get("grade_level") or "初中",
            description=tb.get("description"),
            subject_id=subject_id,
            owner_id=owner_id,
        )
        s.add(textbook)
        s.commit()
        s.refresh(textbook)
        return textbook


def _create_chapter(
    owner_id: uuid.UUID,
    textbook_id: uuid.UUID,
    title: str,
    level: int,
    order_index: int,
    parent_id: uuid.UUID | None,
    kp_id: str | None,
) -> Chapter:
    with Session(engine) as s:
        ch = Chapter(
            title=title,
            level=level,
            order_index=order_index,
            parent_id=parent_id,
            textbook_id=textbook_id,
            owner_id=owner_id,
            knowledge_point_id=uuid.UUID(kp_id) if kp_id else None,
        )
        s.add(ch)
        s.commit()
        s.refresh(ch)
        return ch


def _ensure_kp(
    repo: KnowledgeGraphRepository,
    owner_id: str,
    name: str,
    subject: str,
    grade: str,
    spec: dict,
) -> str:
    existing = repo.find_by_name(name, None)
    if existing:
        return existing["id"]
    kp = repo.create_knowledge_point(
        owner_id=owner_id,
        name=name,
        subject=subject,
        description=spec.get("desc", ""),
        grade_level=grade,
        difficulty=int(spec.get("difficulty", 1)),
        is_key_point=bool(spec.get("key", False)),
    )
    return kp["id"]


def _ensure_exam(repo: KnowledgeGraphRepository, owner_id: str, kp_id: str, exam: dict) -> None:
    existing = repo.get_exam_points(kp_id)
    if any(e.get("name") == exam["name"] for e in existing):
        return
    ep = repo.create_exam_point(
        owner_id=owner_id,
        name=exam["name"],
        level=exam.get("level", "理解"),
        description=exam.get("description", ""),
    )
    repo.link_kp_exam_point(kp_id, ep["id"])


def _ensure_mis(
    repo: KnowledgeGraphRepository, owner_id: str, kp_id: str, mis: dict
) -> None:
    existing = repo.get_misconceptions(kp_id)
    if any(m.get("content") == mis["content"] for m in existing):
        return
    m = repo.create_misconception(
        owner_id=owner_id,
        content=mis["content"],
        correction=mis.get("correction", ""),
    )
    repo.link_kp_misconception(kp_id, m["id"])


def _ensure_document(
    owner_id: uuid.UUID,
    subject_id: uuid.UUID,
    title: str,
    text: str,
    kp_ids: list[str],
) -> Document:
    with Session(engine) as s:
        existing = s.exec(
            select(Document).where(
                Document.original_filename == title, Document.owner_id == owner_id
            )
        ).first()
        if existing:
            return existing
        doc = Document(
            filename=f"{uuid.uuid4()}.txt",
            original_filename=title,
            file_type="txt",
            file_size=len(text.encode("utf-8")),
            file_path="",
            status=DocumentStatus.COMPLETED,
            owner_id=owner_id,
            extracted_text=text,
            summary="（预置示范教材切片，供 RAG 检索）",
            subject_id=subject_id,
            knowledge_point_ids=kp_ids,
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)
        return doc


# ---------------------------------------------------------------------------
# 兼容入口（编排逻辑见 app/initial_data.seed_knowledge_graph）
# ---------------------------------------------------------------------------


def run_seed_demo() -> None:
    """一键灌库脚本入口（兼容旧调用）。

    实际编排逻辑已迁移到 app/initial_data.seed_knowledge_graph
    （在 prestart / 后端启动时自动调用，也与 extraction_graph 抽取结果共享 find_by_name 去重）。
    本函数仅作转发以保持兼容。
    """
    from app.initial_data import seed_knowledge_graph

    seed_knowledge_graph()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_seed_demo()
