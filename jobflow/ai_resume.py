"""简历 AI / 离线润色。

优先调用 DeepSeek；账户无余额或网络异常时自动退回本地规则引擎，
保证「AI 润色」入口在演示环境中始终可用。
"""

import json
import os
import re
from typing import Dict, List, Optional

import httpx

API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
API_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions"


def _has_api() -> bool:
    return bool(API_KEY)


def _extract_json(content: str) -> Optional[dict]:
    if not content:
        return None
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _valid_changes(changes) -> List[Dict]:
    valid = []
    for change in changes or []:
        if not isinstance(change, dict):
            continue
        key = str(change.get("key") or "")
        original = str(change.get("original") or "").strip()
        polished = str(change.get("polished") or "").strip()
        reason = str(change.get("reason") or "").strip()
        if not key or not original or not polished or len(polished) > 1200:
            continue
        if polished == original:
            continue
        valid.append({
            "key": key,
            "original": original[:900],
            "polished": polished,
            "reason": reason[:300] or "表达更专业、更符合岗位描述习惯",
        })
    return valid


def _ask_llm(resume: Dict) -> Optional[List[Dict]]:
    if not _has_api():
        return None
    projects = [{
        "name": str(item.get("name") or ""),
        "period": str(item.get("period") or ""),
        "description": str(item.get("description") or ""),
    } for item in (resume.get("projects") or [])]
    internships = [{
        "company": str(item.get("company") or ""),
        "role": str(item.get("role") or ""),
        "period": str(item.get("period") or ""),
        "description": str(item.get("description") or ""),
    } for item in (resume.get("internships") or [])]
    payload = {
        "model": "deepseek-chat",
        "temperature": 0.4,
        "max_tokens": 2400,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是资深大学生简历润色顾问。只润色用户提供的自我介绍、项目经历描述与实习经历描述，"
                    "不得虚构经历、技能、数据或成果，不得改变事实，不得删减关键信息。"
                    "输出合法 JSON，不要 Markdown。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "任务": "润色简历文字。请让表达更专业、更有结构、更符合岗位描述习惯，并把松散短句合并成 1-3 句。",
                    "求职方向": resume.get("target_direction") or resume.get("target_role") or "未知",
                    "输出格式": {
                        "changes": [{
                            "key": "intro | project-0 | project-1 ... | intern-0 | intern-1 ...",
                            "original": "原文（必须与输入完全一致）",
                            "polished": "润色后的文本",
                            "reason": "一句话说明为什么这样改",
                        }]
                    },
                    "简历内容": {
                        "self_intro": resume.get("self_intro", ""),
                        "projects": projects,
                        "internships": internships,
                    },
                }, ensure_ascii=False),
            },
        ],
    }
    try:
        response = httpx.post(
            API_URL,
            headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        return _valid_changes(parsed.get("changes") if parsed else None)
    except (httpx.HTTPError, KeyError, IndexError, TypeError):
        return None


_ACTION_VERBS = [
    "负责", "承担", "参与", "主导", "独立完成", "搭建", "开发", "设计", "撰写",
    "完成", "协助", "组织", "推动", "分析", "处理", "运营", "跟进",
    "策划", "支持", "编写", "优化", "统筹",
]

_INTRO_PHRASES = [
    ("经验很丰富", "实践经验扎实"),
    ("经验丰富", "实践经验扎实"),
    ("熟悉...", "熟悉"),
    ("熟练运用", "熟练使用"),
    ("学习能力很强", "学习能力强"),
    ("有较强的学习能力", "学习能力强"),
    ("具有较强的", "具备较强的"),
]


def _polish_text(text: str, kind: str) -> Dict:
    original = re.sub(r"\s+", " ", text or "").strip()
    if not original:
        return {"original": "", "polished": "", "reason": ""}
    polished = original
    reason = ""

    if kind == "intro":
        for old, new in _INTRO_PHRASES:
            if old in polished:
                polished = polished.replace(old, new)
                reason = "将模糊表述改成更可读的自我定位"
        polished = re.sub(r"^我(?:是|来自|的|在)?", "", polished).strip()
        if polished and not polished.endswith(("。", "！", "！", "；")):
            polished += "。"
        if not reason:
            reason = "压缩冗余词，使定位更清晰"
        return {"original": original, "polished": polished, "reason": reason}

    if kind in ("project", "intern"):
        polished = re.sub(r"^(本人|自己)\s*", "", polished)
        if polished.startswith("扮演"):
            polished = re.sub(
                r"^扮演(.+?)，?",
                r"统筹承担\1等相关职责，",
                polished,
            )
            reason = "把角色描述改写成简历常用的成果导向句式"
        role_match = re.match(r"^担任([^，,；;。]{1,24})(.*)$", polished)
        if role_match:
            role = role_match.group(1).strip()
            suffix = role_match.group(2).strip()
            polished = "承担" + role + "职责" + (("，" + suffix) if suffix else "，推进相关工作落地")
            reason = "用「承担职责 + 结果」句式替换角色陈述，提升专业度"
        action_match = re.match(rf"^({'|'.join(_ACTION_VERBS)})", polished)
        if not action_match:
            polished = "负责" + polished
            reason = "补充明确的动作主语，让经历描述更主动"
        polished = re.sub(r"[，,]\s*(使用|通过|借助)", "；\1", polished)
        polished = re.sub(r"(?<=[\u4e00-\u9fa5])\s{2,}(?=[\u4e00-\u9fa5])", " ", polished)
        if polished and not polished.endswith(("。", "！", "；")):
            polished += "。"
        if not reason:
            reason = "统一句式并补全标点，提高机器阅读与 HR 阅读效率"
        return {"original": original, "polished": polished, "reason": reason}
    return {"original": original, "polished": polished, "reason": ""}


def polish_resume(resume: Dict) -> Dict:
    """返回可预览、可逐条采纳的润色建议。"""
    changes = []
    source = "deepseek"
    if _has_api():
        changes = _ask_llm(resume) or []
    if changes:
        source = "deepseek"
    else:
        source = "local"
        intro = _polish_text(resume.get("self_intro", ""), "intro")
        if intro.get("polished") and intro.get("polished") != intro.get("original"):
            changes.append({"key": "intro", **intro})
        for index, project in enumerate(resume.get("projects") or []):
            result = _polish_text(project.get("description", ""), "project")
            if result.get("polished"):
                result["key"] = f"project-{index}"
                changes.append(result)
        for index, internship in enumerate(resume.get("internships") or []):
            result = _polish_text(internship.get("description", ""), "intern")
            if result.get("polished"):
                result["key"] = f"intern-{index}"
                changes.append(result)

    note = (
        "AI 润色已接入 DeepSeek。"
        if source == "deepseek"
        else "DeepSeek 暂不可用，本次使用离线润色引擎生成建议，内容不会上传。"
    )
    if not changes:
        note = "暂无值得改写的文字，请先完善自我介绍或项目 / 实习描述。"
    return {
        "source": source,
        "note": note,
        "changes": changes,
    }
