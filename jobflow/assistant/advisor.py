"""职航回答顾问：先规则检索与工具取数，再组装可溯源答案。

设计上不把模型当作知识源：个人数据从 store/service 读取，
公开方法论从种子知识库检索，题目从结构化题库读取。
后续可在此层之上接入 DeepSeek 作为自由表达层。
"""

from typing import Dict, List, Optional

import re

from jobflow.assistant.knowledge import KNOWLEDGE
from jobflow.assistant.question_bank import QUESTIONS
from jobflow.matching import extract_skills
from jobflow.service import dashboard, recommendation_items

DIRECTION_WORDS = {
    "后端": ["后端", "java", "go", "spring", "mysql", "redis", "服务端"],
    "前端": ["前端", "vue", "react", "typescript", "html", "css", "web"],
    "算法": ["算法", "机器学习", "深度学习", "大模型", "pytorch", "推荐", "nlp"],
    "数据": ["数据", "sql", "数据分析", "运营分析", "bi", "ab测试", "报表"],
    "产品": ["产品", "pm", "需求", "prd", "原型", "用户研究"],
    "运营": ["运营", "增长", "活动", "内容运营", "用户运营"],
}


def _tokens(text: str) -> set:
    """轻量中文分词：保留完整词 + 二元字符片段，足够用于种子知识检索。"""
    tokens = set()
    for part in re.findall(r"[A-Za-z0-9+#./_-]+|[\u4e00-\u9fa5]+", str(text or "").lower()):
        if not part:
            continue
        if re.match(r"^[A-Za-z0-9+#./_-]+$", part):
            if len(part) >= 2:
                tokens.add(part)
            continue
        tokens.add(part)
        if len(part) > 2:
            tokens.update(part[index:index + 2] for index in range(len(part) - 1))
    return tokens


def direction_of(message: str, resume: Optional[Dict]) -> str:
    text = str(message or "").lower()
    for direction, words in DIRECTION_WORDS.items():
        if any(word in text for word in words):
            return direction
    if resume and resume.get("target_direction"):
        return str(resume.get("target_direction"))
    return ""


def detect_intent(message: str) -> str:
    text = str(message or "")
    if "进度" in text or "状态" in text or any(word in text for word in ["投递记录", "现在到哪一步", "offer了吗"]):
        return "status"
    if "笔试题" in text or "题库" in text or "真题" in text or "刷题" in text or "笔试考" in text:
        return "question"
    if "简历" in text and any(word in text for word in ["怎么改", "优化", "诊断", "建议", "评价", "分析", "怎么样", "行不行"]):
        return "resume"
    if any(word in text for word in ["匹配", "岗位", "适合", "投递", "投什么", "去投", "机会"]):
        return "job"
    if any(word in text for word in ["怎么准备", "准备", "要学什么", "重点", "入门", "路线", "怎么学", "应该学"]):
        return "prep"
    return "knowledge"


def retrieve_knowledge(message: str, resume: Optional[Dict], intent: str, limit: int = 2) -> List[Dict]:
    query_tokens = _tokens(message)
    resume_direction = resume.get("target_direction", "") if resume else ""
    direction = direction_of(message, resume)
    scored = []
    for doc in KNOWLEDGE:
        doc_direction = doc.get("direction", "")
        if direction and doc_direction and doc_direction != direction:
            continue
        if not direction and resume_direction and doc_direction and doc_direction != resume_direction:
            continue
        haystack = " ".join([
            doc.get("title", ""),
            doc.get("kind", ""),
            " ".join(doc.get("keywords", [])),
            " ".join(block.get("title", "") + " " + block.get("body", "")
                     + " " + " ".join(block.get("points", []))
                     for block in doc.get("blocks", [])),
        ])
        tokens = _tokens(haystack)
        score = len(query_tokens & tokens)
        if doc_direction == direction:
            score += 6
        if doc_direction == resume_direction:
            score += 2
        if intent == "resume" and doc.get("id") == "method-resume":
            score += 5
        if doc.get("id") in ("method-strategy", "method-interview"):
            score += 1
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[:limit]]


def _resume_advice(store: Dict, message: str) -> Dict:
    resume = store.get("resume")
    if not resume:
        return {
            "intent": "resume",
            "reply": (
                "我还没读到你的简历，暂时无法做诊断。\n"
                "请先到「简历」页完成求职意向、教育、项目或实习中的任意一项并保存，"
                "我就能结合你的技能缺口和目标方向给建议。"
            ),
            "sources": ["简历方法论"],
            "suggestions": ["后端实习怎么准备", "帮我推荐几道笔试题", "求职进度到哪一步了"],
        }

    skills = extract_skills(resume)
    education = resume.get("education") or []
    projects = resume.get("projects") or []
    internships = resume.get("internships") or []
    honors = resume.get("honors") or []
    problems = []
    if not resume.get("target_role"):
        problems.append("还没有明确的求职意向，岗位匹配只能依赖技能与文字识别。")
    if not education:
        problems.append("教育经历为空，建议补充学校、专业、学历与在读时间。")
    if not projects and not internships:
        problems.append("项目和实习都为空，这是目前最大的短板。")
    elif not projects:
        problems.append("没有项目经历，建议至少补一个能体现技术栈与成果的项目。")
    if len(skills) < 3:
        problems.append("技能标签不足 3 个，岗位检索时很容易错过关键词。")

    top_recommendation = None
    if resume and (resume.get("target_role") or resume.get("target_direction")):
        items = recommendation_items(store, limit=1)
        top_recommendation = items[0] if items else None

    reply_lines = ["【简历顾问】我已经读取当前简历，先给你三个判断："]
    reply_lines.append("")
    if problems:
        reply_lines.extend(f"{i + 1}. {problem}" for i, problem in enumerate(problems[:4]))
    else:
        reply_lines.append("1. 简历主干结构完整，方向、教育、项目和技能都有覆盖。")
    reply_lines.append("")
    reply_lines.append("目前简历画像：" + (
        f"{resume.get('target_role') or '方向未定'} · "
        f"技能 {len(skills)} 个 · 项目 {len(projects)} 个 · 实习 {len(internships)} 个"
    ))
    if honors:
        reply_lines.append(f"荣誉奖项 {len(honors)} 项已保留，技术岗简历建议只突出与岗位最相关的 2-3 项。")
    if top_recommendation:
        job = top_recommendation["job"]
        match = top_recommendation["match"]
        reply_lines.append("")
        reply_lines.append(f"按当前简历最匹配的岗位是「{job['company']} · {job['title']}」")
        if match.get("missing_skills"):
            reply_lines.append("重点补强：" + "、".join(match["missing_skills"]))
    reply_lines.append("")
    reply_lines.append("修改顺序建议：先补最影响匹配的岗位关键词，再优化每条经历的「动作 + 技术 + 量化结果」。")

    method = retrieve_knowledge("简历怎么优化", resume, "resume", limit=1)
    if method:
        block = method[0]["blocks"][0]
        reply_lines.append("")
        reply_lines.append(block["title"] + "：" + block["body"])

    return {
        "intent": "resume",
        "reply": "\n".join(reply_lines),
        "sources": ["当前简历数据", *(doc["title"] for doc in method)],
        "suggestions": ["后端实习怎么准备", "看看岗位匹配结果", "帮我推荐笔试真题"],
    }


def _job_advice(store: Dict, message: str) -> Dict:
    resume = store.get("resume")
    if not resume:
        return {
            "intent": "job",
            "reply": (
                "要做岗位匹配，需要先有一份简历。\n"
                "你可以先到「简历」页一键填写示例或上传已有简历，保存后我立刻帮你分析。"
            ),
            "sources": ["岗位匹配引擎"],
            "suggestions": ["后端实习怎么准备", "帮我推荐几道笔试题", "求职进度到哪一步了"],
        }

    company_hint = ""
    for company in ["字节", "腾讯", "阿里巴巴", "美团", "阿里"]:
        if company in message:
            company_hint = company.replace("阿里巴巴", "阿里巴巴").replace("阿里", "阿里巴巴")
            break
    candidates = recommendation_items(store, limit=4)
    if company_hint:
        company_candidates = [
            item for item in candidates
            if company_hint in (item["job"].get("company") or "")
        ]
        if company_candidates:
            candidates = company_candidates

    if not candidates:
        return {
            "intent": "job",
            "reply": "按当前简历没有检索到足够匹配的岗位。建议先补目标方向与技能，再来看机会。",
            "sources": ["岗位匹配引擎"],
            "suggestions": ["去完善简历", "后端实习怎么准备"],
        }

    lines = ["【岗位顾问】我按技能、方向、行业、城市四类信息做了匹配，结论如下："]
    for index, item in enumerate(candidates[:3], 1):
        job = item["job"]
        match = item["match"]
        lines.append("")
        lines.append(f"{index}. {job['company']} · {job['title']}（匹配 {match['score']}%）")
        lines.append(f"   地点：{job['city']} · {job['type']} · {job['pay']}")
        if match.get("matched_skills"):
            lines.append("   已命中：" + "、".join(match["matched_skills"][:5]))
        if match.get("missing_skills"):
            lines.append("   待补强：" + "、".join(match["missing_skills"][:5]))
        lines.append("")
    max_score = max((item["match"]["score"] for item in candidates[:3]), default=0)
    if max_score < 60:
        lines.append("建议：当前最高匹配度只有 " + str(max_score) + "%，说明技能画像和目标岗位仍有差距，先按缺口补 2-3 个关键点再投递。")
    else:
        lines.append("建议：优先投 80% 以上且缺口技能较少的岗位；60%-80% 的岗位先补 1-2 个关键技能再投。")

    strategy = retrieve_knowledge("投递策略 岗位匹配", resume, "job", limit=1)
    return {
        "intent": "job",
        "reply": "\n".join(lines),
        "sources": ["当前岗位库", *(doc["title"] for doc in strategy)],
        "suggestions": ["去机会速览投递", "这份简历适合什么方向", "后端实习怎么准备"],
    }


def _question_advice(store: Dict, message: str) -> Dict:
    resume = store.get("resume")
    direction = direction_of(message, resume)
    matched = [
        q for q in QUESTIONS
        if (direction and q["direction"] == direction) or (direction and direction in q.get("topic", ""))
    ]
    company_hint = ""
    for company in ["字节", "腾讯", "阿里巴巴", "美团", "阿里"]:
        if company in message:
            company_hint = company.replace("阿里", "阿里巴巴")
            break
    if company_hint:
        company_matched = [q for q in matched if company_hint in q.get("company", "")]
        if company_matched:
            matched = company_matched
    if not matched and not direction:
        matched = QUESTIONS[:3]
    if not matched:
        matched = [q for q in QUESTIONS if q["direction"] == (resume or {}).get("target_direction")][:3]
    if not matched:
        matched = QUESTIONS[:3]

    lines = ["【题库顾问】先按方向为你筛了种子真题，完整题库后续接入："]
    for index, q in enumerate(matched[:3], 1):
        lines.append("")
        lines.append(f"{index}. [{q['company']}·{q['topic']}·{q['difficulty']}] {q['question']}")
        lines.append(f"   解析方向：{q['reference']}")
    lines.append("")
    lines.append("建议不要只背答案：先口述一遍，再对照参考点检查是否覆盖适用场景和边界条件。")
    return {
        "intent": "question",
        "reply": "\n".join(lines),
        "sources": ["结构化种子题库", *(q["company"] + q["topic"] for q in matched[:3])],
        "suggestions": ["模拟一次后端一面", "简历现在适合投什么", "投递进度到哪了"],
    }


def _prep_advice(store: Dict, message: str) -> Dict:
    resume = store.get("resume")
    direction = direction_of(message, resume)
    docs = retrieve_knowledge(message, resume, "prep", limit=2)
    if not docs:
        docs = retrieve_knowledge("岗位准备路线 技能 项目", resume, "prep", limit=2)

    lines = ["【备考顾问】给你一条先练框架、再补题目的路线："]
    if direction:
        lines.append(f"识别到方向：{direction}")
    lines.append("")
    for doc in docs[:2]:
        for block in doc.get("blocks", [])[:2]:
            lines.append(f"{block['title']}：{block['body']}")
            for point in block.get("points", [])[:3]:
                lines.append("  - " + point)
            lines.append("")

    question_hint = _question_advice(store, message)
    lines.append("参考题目（种子题库）：")
    for line in question_hint["reply"].splitlines():
        if line.startswith(("1.", "2.", "3.")):
            lines.append("  " + line)

    return {
        "intent": "prep",
        "reply": "\n".join(lines),
        "sources": [doc["title"] for doc in docs],
        "suggestions": ["看看岗位匹配", "帮我优化简历", "模拟一次技术面试"],
    }


def _status_advice(store: Dict) -> Dict:
    dash = dashboard(store)
    progress = dash["progress"]
    lines = ["【求职状态】当前工作台进度："]
    lines.append(f"已完成 {progress['done_count']} / {progress['total']} 步。")
    for step in progress["steps"]:
        marker = "✓" if step["state"] == "done" else ("→" if step["state"] == "current" else "·")
        lines.append(f"{marker} {step['label']}：{step['desc']}")
    lines.append("")
    if dash["tasks"]:
        lines.append("今天建议先做：" + "；".join(task["title"] for task in dash["tasks"][:3]))
    stats = dash["stats"]
    lines.append(f"投递 {stats['applications']} · 面试中 {stats['in_interview']} · Offer {stats['offers']}")
    return {
        "intent": "status",
        "reply": "\n".join(lines),
        "sources": ["工作台聚合数据"],
        "suggestions": ["帮我看看匹配岗位", "简历应该怎么改", "后端实习怎么准备"],
    }


def _knowledge_fallback(message: str, resume: Optional[Dict]) -> Dict:
    docs = retrieve_knowledge(message, resume, "knowledge", limit=2)
    if not docs:
        return {
            "intent": "knowledge",
            "reply": (
                "我现在能回答的问题主要围绕：岗位怎么准备、简历怎么改、真题怎么刷、"
                "当前进度怎么看。你可以换一种说法再问我。"
            ),
            "sources": [],
            "suggestions": ["后端实习怎么准备", "我的简历适合什么岗位", "有什么笔试题可以先看"],
        }
    lines = [f"【{doc['title']}】" for doc in docs]
    for doc in docs:
        for block in doc.get("blocks", [])[:2]:
            lines.append("")
            lines.append(f"{block['title']}：{block['body']}")
            for point in block.get("points", [])[:3]:
                lines.append("  - " + point)
    lines.append("")
    lines.append("以上内容来自种子知识库。如果你想绑定某个岗位或简历，可以直接问“我和某岗位匹配吗”。")
    return {
        "intent": "knowledge",
        "reply": "\n".join(lines),
        "sources": [doc["title"] for doc in docs],
        "suggestions": ["我和字节后端匹配吗", "我的简历应该怎么改", "后端实习怎么准备"],
    }


def advise(store: Dict, message: str) -> Dict:
    """回答顾问主入口：意图路由后返回本地可溯源回答。"""
    message = (message or "").strip()
    intent = detect_intent(message)
    if intent == "resume":
        result = _resume_advice(store, message)
    elif intent == "job":
        result = _job_advice(store, message)
    elif intent == "question":
        result = _question_advice(store, message)
    elif intent == "status":
        result = _status_advice(store)
    elif intent == "prep":
        result = _prep_advice(store, message)
    else:
        result = _knowledge_fallback(message, store.get("resume"))
    result["engine"] = "local"
    result["message"] = message
    return result
