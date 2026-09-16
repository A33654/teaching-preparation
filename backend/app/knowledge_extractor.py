"""知识抽取器：从文本中自动识别知识点和关系"""

import re
from collections import Counter


# 中文学科关键词库
SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "数学": [
        "定理", "公式", "方程", "函数", "几何", "代数", "概率", "统计",
        "三角", "数列", "导数", "积分", "向量", "矩阵", "集合", "映射",
        "勾股", "平方", "立方", "圆", "角", "面积", "体积",
    ],
    "物理": [
        "定律", "力学", "运动", "能量", "电场", "磁场", "光学", "热学",
        "牛顿", "速度", "加速度", "力", "功", "功率", "电阻", "电压",
        "电流", "波动", "量子", "原子", "核",
    ],
    "化学": [
        "元素", "反应", "化学式", "分子", "原子", "离子", "化合物",
        "氧化", "还原", "酸碱", "溶液", "催化剂", "电解", "有机",
    ],
    "语文": [
        "修辞", "文言文", "诗词", "散文", "小说", "议论文", "说明文",
        "作者", "朝代", "主旨", "意境", "手法",
    ],
    "英语": [
        "语法", "时态", "词汇", "从句", "阅读", "写作", "听力", "口语", "翻译",
    ],
    "历史": ["朝代", "战争", "革命", "制度", "文化", "人物", "事件"],
    "地理": ["地形", "气候", "人口", "资源", "区域", "国家", "河流"],
    "生物": ["细胞", "基因", "遗传", "进化", "生态", "光合", "呼吸"],
}

# 中文关系暗示词
RELATION_HINTS = {
    "prerequisite": ["前置", "基础", "先学", "预备", "前提", "需要先掌握", "建立在"],
    "contains": ["包括", "分为", "包含", "涵盖", "细分"],
    "related_to": ["相关", "关联", "延伸", "扩展", "类似", "参见"],
}

# 常见非知识点词汇（精确匹配和包含匹配）
STOP_WORDS = {"是数学中", "是一个", "是一种", "定义为", "被称为", "重要的", "基本的"}
# 不应作为知识点开头的字
BAD_PREFIXES = {"是", "的", "在", "和", "与", "或", "中", "被", "把", "从", "对"}


def detect_subject(text: str) -> str:
    """通过关键词匹配检测学科"""
    scores: Counter = Counter()
    for subject, keywords in SUBJECT_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[subject] += 1
    if scores:
        return scores.most_common(1)[0][0]
    return "通用"


def extract_knowledge_points(text: str) -> list[dict]:
    """
    从文本中抽取知识点。
    返回 list[{"name": str, "description": str, "subject": str, "confidence": float}]
    """
    knowledge_points: list[dict] = []
    subject = detect_subject(text)

    # 匹配模式：(最小长度, 后缀词列表, 置信度)
    pattern_specs = [
        (3, ["定理", "定律", "公式", "原理", "法则", "公理"], 0.8),
        (2, ["函数", "方程", "不等式", "数列"], 0.6),
        (2, ["反应", "元素", "化合物"], 0.6),
        (3, ["概念", "定义", "性质", "特点", "分类"], 0.5),
    ]

    seen_names: set[str] = set()
    for min_len, suffixes, confidence in pattern_specs:
        suffix_pattern = "|".join(suffixes)
        regex = re.compile(
            r"([一-鿿]{" + str(min_len) + r",8}(?:" + suffix_pattern + r"))"
        )
        for match in regex.finditer(text):
            name = match.group(1)
            if name not in seen_names and len(name) >= min_len:
                if any(sw in name for sw in STOP_WORDS):
                    continue
                if name[0] in BAD_PREFIXES:
                    continue
                seen_names.add(name)
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 60)
                context = text[start:end].replace("\n", " ").strip()
                knowledge_points.append({
                    "name": name,
                    "description": context,
                    "subject": subject,
                    "confidence": confidence,
                })

    return knowledge_points


def extract_relations(text: str, knowledge_points: list[dict]) -> list[dict]:
    """
    从文本中识别知识点之间的关系。
    返回 list[{"source_name": str, "target_name": str, "relation_type": str}]
    """
    relations: list[dict] = []
    kp_names = [kp["name"] for kp in knowledge_points]

    for i, kp_a in enumerate(kp_names):
        for j, kp_b in enumerate(kp_names):
            if i >= j:
                continue
            pattern = re.compile(re.escape(kp_a) + r"[\s\S]{0,50}" + re.escape(kp_b))
            for match in pattern.finditer(text):
                context = match.group()
                for rel_type, hints in RELATION_HINTS.items():
                    for hint in hints:
                        if hint in context:
                            relations.append({
                                "source_name": kp_a,
                                "target_name": kp_b,
                                "relation_type": rel_type,
                            })
                            break

    return relations


def analyze_document(text: str) -> dict:
    """
    综合分析文档，返回抽取结果。
    {
        "subject": str,
        "knowledge_points": list[dict],
        "relations": list[dict],
    }
    """
    subject = detect_subject(text)
    kps = extract_knowledge_points(text)
    relations = extract_relations(text, kps)
    return {
        "subject": subject,
        "knowledge_points": kps,
        "relations": relations,
    }
