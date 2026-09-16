"""统一 LLM 客户端 —— 千问优先，DeepSeek 备用"""
import json
import httpx
from app.core.config import settings


def _get_llm_config():
    """获取可用的 LLM 配置，千问优先"""
    if settings.QWEN_API_KEY and settings.QWEN_API_KEY != "your-qwen-api-key":
        return {
            "api_key": settings.QWEN_API_KEY,
            "base_url": settings.QWEN_BASE_URL,
            "model": settings.QWEN_MODEL,
            "name": "qwen",
        }
    if settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY != "your-deepseek-api-key":
        return {
            "api_key": settings.DEEPSEEK_API_KEY,
            "base_url": settings.DEEPSEEK_BASE_URL,
            "model": settings.DEEPSEEK_MODEL,
            "name": "deepseek",
        }
    raise RuntimeError("未配置任何 LLM API Key，请在 .env 中设置 QWEN_API_KEY 或 DEEPSEEK_API_KEY")


def _call_llm(system_prompt: str, user_message: str, temperature: float = 0.3, max_tokens: int = 4000) -> str:
    """调用 LLM API（千问优先），返回响应文本"""
    cfg = _get_llm_config()
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _parse_json_response(response: str) -> dict:
    """解析 LLM 返回的 JSON"""
    cleaned = response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return json.loads(cleaned)


# Legacy alias
_call_deepseek = _call_llm


def extract_knowledge_with_llm(text: str) -> dict:
    """使用 LLM 从文本提取知识点和关系"""
    truncated = text[:8000] if len(text) > 8000 else text
    prompt = (
        "你是教育知识图谱专家。从文档提取知识点和它们的关系。"
        "返回JSON格式: {\"subject\":\"学科\",\"knowledge_points\":[{\"name\":\"知识点名\",\"description\":\"简述\",\"confidence\":0.9,\"subject\":\"学科\"}],\"relations\":[{\"source_name\":\"源知识点\",\"target_name\":\"目标知识点\",\"relation_type\":\"prerequisite|contains|related_to\"}]}"
        "规则: 知识点名称要简洁精准，confidence 0-1表达把握，relation_type只取prerequisite/contains/related_to"
    )
    result = _call_llm(prompt, truncated, temperature=0.2, max_tokens=3000)
    return _parse_json_response(result)


def generate_lesson_plan_with_llm(
    knowledge_points: list[dict],
    subject: str = "",
    grade_level: str = "",
    extra_context: str = "",
) -> dict:
    """使用 LLM 生成教案"""
    kp_text = "\n".join([f"- {kp.get('name', kp)}: {kp.get('description', '')}" for kp in knowledge_points])
    prompt = (
        "你是资深教师。根据知识点生成完整教案JSON: "
        "{\"title\":\"教案标题\",\"subject\":\"学科\",\"grade_level\":\"学段\",\"teaching_objectives\":\"教学目标\",\"teaching_process\":\"详细教学过程(含时间分配)\",\"key_points\":[\"重点\"],\"difficult_points\":[\"难点\"]}"
        "teaching_process要详细具体，每个环节3-5句话"
    )
    user_msg = f"知识点:\n{kp_text}\n学科:{subject or '通用'}\n学段:{grade_level or '初中'}\n要求:{extra_context}"
    result = _call_llm(prompt, user_msg, temperature=0.7, max_tokens=3000)
    return _parse_json_response(result)
