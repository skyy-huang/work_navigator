"""简历 × 岗位 匹配引擎（v1：确定性关键词/技能匹配，无需外部 AI）"""

from typing import Dict, List, Optional

# 可被识别的技能/关键词词典：从简历文本中自动识别
SKILL_KEYWORDS = [
    "java", "spring boot", "spring", "mysql", "redis", "kafka", "分布式", "高并发",
    "微服务", "linux", "golang", "go", "c++", "cpp", "python", "pytorch",
    "tensorflow", "机器学习", "深度学习", "nlp", "数据结构", "算法", "操作系统",
    "计算机网络", "jvm", "docker", "kubernetes", "k8s", "多线程", "sql", "excel",
    "powerpoint", "ppt", "数据分析", "数据仓库", "etl", "flink", "spark", "hadoop",
    "ab测试", "a/b测试", "指标体系", "用户研究", "需求分析", "竞品分析", "市场调研",
    "行业研究", "项目管理", "结构化思维", "量化", "金融", "axure", "typescript",
    "javascript", "vue", "react", "css", "http", "html", "小程序", "沟通表达",
    "工业工程", "新媒体", "增长", "后端", "前端", "算法", "产品", "运营",
]

# 关键词展示名修正（检测到 cpp 展示为 C++）
_DISPLAY_OVERRIDES = {
    "cpp": "C++",
    "c++": "C++",
    "golang": "Go",
    "go": "Go",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "k8s": "Kubernetes",
    "ppt": "PowerPoint",
    "ab测试": "A/B测试",
    "java": "Java",
    "sql": "SQL",
    "mysql": "MySQL",
    "redis": "Redis",
    "linux": "Linux",
    "python": "Python",
    "spring": "Spring",
    "spring boot": "Spring Boot",
    "kafka": "Kafka",
    "vue": "Vue",
    "react": "React",
    "excel": "Excel",
    "axure": "Axure",
    "docker": "Docker",
    "jvm": "JVM",
    "css": "CSS",
    "http": "HTTP",
    "html": "HTML",
    "pytorch": "PyTorch",
}


def _display(name: str) -> str:
    return _DISPLAY_OVERRIDES.get(name.lower(), name)


def extract_skills(resume: Dict) -> List[str]:
    """从简历结构化字段中提取技能集合（显式技能 + 文本识别）。"""
    if not resume:
        return []
    parts = [
        resume.get("self_intro", ""),
        resume.get("target_role", ""),
    ]
    for edu in resume.get("education", []) or []:
        parts.append(" ".join(str(v) for v in edu.values()))
    for proj in resume.get("projects", []) or []:
        parts.append(" ".join(str(v) for v in proj.values()))
    for inter in resume.get("internships", []) or []:
        parts.append(" ".join(str(v) for v in inter.values()))
    corpus = " ".join(parts).lower()

    found = set()
    for kw in SKILL_KEYWORDS:
        if kw.lower() in corpus:
            found.add(kw)
    for skill in resume.get("skills", []) or []:
        if str(skill).strip():
            found.add(str(skill).strip().lower())
    return [_display(s) for s in sorted(found)]


def _token_set(values) -> List[str]:
    out = []
    for value in values or []:
        value = str(value).strip()
        if value and value not in out:
            out.append(value)
    return out


def match_job(resume: Dict, job: Dict) -> Optional[Dict]:
    """计算单份简历与单个岗位的匹配度。无简历时返回 None。"""
    if not resume:
        return None

    skills = [s.lower() for s in extract_skills(resume)]
    corpus = " ".join(skills)
    required = [str(s).lower() for s in job.get("skills", [])]
    matched = []
    missing = []
    for req in required:
        if req in corpus:
            matched.append(req)
        else:
            missing.append(req)

    if required:
        skill_ratio = len(matched) / len(required)
    else:
        skill_ratio = 0.5

    target_direction = str(resume.get("target_direction", "") or "").lower().strip()
    target_industry = str(resume.get("target_industry", "") or "").lower().strip()
    target_city = str(resume.get("target_city", "") or "").lower().strip()

    job_text = " ".join([
        job.get("title", ""), job.get("industry", ""), job.get("city", ""),
        " ".join(job.get("tags", []) or []),
    ]).lower()

    direction_matched = bool(target_direction and target_direction in job_text)
    industry_matched = bool(target_industry and target_industry in job_text)
    city_matched = bool(target_city and target_city in job_text)

    score = round(
        100 * (
            0.62 * skill_ratio
            + 0.22 * (1 if direction_matched else 0)
            + 0.10 * (1 if industry_matched else 0)
            + 0.06 * (1 if city_matched else 0)
        )
    )
    score = max(8, min(score, 98))

    return {
        "score": score,
        "matched_skills": [_display(s) for s in matched[:8]],
        "missing_skills": [_display(s) for s in missing[:6]],
        "direction_matched": direction_matched,
        "industry_matched": industry_matched,
        "city_matched": city_matched,
    }


def recommend(resume: Dict, jobs: List[Dict], limit: Optional[int] = None):
    """按匹配度从高到低推荐岗位。"""
    if not resume:
        return []
    scored = []
    for job in jobs:
        match = match_job(resume, job)
        scored.append((match["score"], job, match))
    scored.sort(key=lambda item: item[0], reverse=True)
    items = scored[:limit] if limit else scored
    return [{"job": job, "match": match} for _, job, match in items]
