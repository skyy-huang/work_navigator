"""职航聚合服务：岗位/投递/工作台进度等业务逻辑"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from jobflow.matching import extract_skills, match_job, recommend

STATUS_ORDER = ["已投递", "待笔试", "已笔试", "面试中", "Offer"]
INDUSTRIES = ["互联网", "金融", "快消", "制造", "咨询"]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def status_index(status: str) -> int:
    try:
        return STATUS_ORDER.index(status)
    except ValueError:
        return 0


def job_summary(job: Dict) -> Dict:
    keys = ["id", "company", "title", "industry", "city", "type", "pay", "tags"]
    return {key: job.get(key) for key in keys}


def application_view(store: Dict, application: Dict) -> Dict:
    jobs_by_id = {job["id"]: job for job in store["jobs"]}
    job = jobs_by_id.get(application.get("job_id"))
    resume = store.get("resume")
    match = match_job(resume, job) if resume and job else None
    return {
        "id": application.get("id"),
        "job": job_summary(job) if job else None,
        "applied_at": application.get("applied_at"),
        "status": application.get("status", "已投递"),
        "status_order": status_index(application.get("status", "已投递")),
        "match": match,
    }


def create_application(store: Dict, job_id: str) -> Optional[Dict]:
    if any(app.get("job_id") == job_id for app in store["applications"]):
        return None  # 已投递过
    application = {
        "id": "app-" + uuid.uuid4().hex[:8],
        "job_id": job_id,
        "applied_at": now_text(),
        "status": "已投递",
    }
    store["applications"].append(application)
    return application


def advance_application(store: Dict, application_id: str) -> Optional[Dict]:
    for application in store["applications"]:
        if application["id"] != application_id:
            continue
        current = status_index(application.get("status", "已投递"))
        if current < len(STATUS_ORDER) - 1:
            application["status"] = STATUS_ORDER[current + 1]
        return application
    return None


def remove_application(store: Dict, application_id: str) -> bool:
    for idx, application in enumerate(store["applications"]):
        if application["id"] == application_id:
            store["applications"].pop(idx)
            return True
    return False


def jobs_list(
    store: Dict,
    industry: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict]:
    resume = store.get("resume")
    result = []
    for job in store["jobs"]:
        if industry and industry != "全部" and job.get("industry") != industry:
            continue
        if query:
            haystack = " ".join([
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
                " ".join(job.get("tags", []) or []),
                " ".join(job.get("skills", []) or []),
            ]).lower()
            if query.lower() not in haystack:
                continue
        item = job_summary(job)
        item["match"] = match_job(resume, job) if resume else None
        result.append(item)
    return result


def recommendation_items(store: Dict, limit: int = 4) -> List[Dict]:
    resume = store.get("resume")
    if not resume:
        return []
    items = recommend(resume, store["jobs"], limit=limit)
    out = []
    for item in items:
        out.append({
            "job": job_summary(item["job"]),
            "match": item["match"],
        })
    return out


def progress_steps(store: Dict) -> Dict:
    resume = store.get("resume")
    applications = store.get("applications", [])
    highest = max(
        (status_index(app.get("status", "已投递")) for app in applications),
        default=-1,
    )
    resume_ok = resume is not None
    steps = [
        {"key": "intent", "label": "求职意向", "desc": "明确方向与目标岗位", "done": resume_ok},
        {"key": "resume", "label": "简历创建", "desc": "完善教育/项目/实习经历", "done": resume_ok},
        {"key": "apply", "label": "岗位投递", "desc": "投递匹配岗位", "done": len(applications) > 0},
        {"key": "test", "label": "笔试备战", "desc": "通过笔试环节", "done": highest >= 2},
        {"key": "interview", "label": "面试冲刺", "desc": "进入面试环节", "done": highest >= 3},
        {"key": "offer", "label": "Offer 决策", "desc": "拿下心仪 Offer", "done": highest >= 4},
    ]
    done_count = sum(1 for step in steps if step["done"])
    first_open = next((i for i, step in enumerate(steps) if not step["done"]), None)
    for i, step in enumerate(steps):
        if step["done"]:
            step["state"] = "done"
        elif first_open == i:
            step["state"] = "current"
            if i == 0:
                step["desc"] = "保存简历即完成前两步"
        else:
            step["state"] = "todo"
    return {"steps": steps, "done_count": done_count, "total": len(steps)}


def build_tasks(store: Dict) -> List[Dict]:
    resume = store.get("resume")
    applications = store.get("applications", [])
    tasks = []
    if not resume:
        tasks.append({
            "key": "resume",
            "title": "创建第一份简历：求职意向 + 教育 + 项目经历",
            "chip": "简历",
            "link": "#/resume",
            "cta": "去创建",
        })
        return tasks
    tasks.append({
        "key": "polish",
        "title": "补充项目经历中的技术栈与量化指标",
        "chip": "简历",
        "link": "#/resume",
        "cta": "去完善",
    })
    if not applications:
        tasks.append({
            "key": "apply",
            "title": "按匹配度投递 3 个心仪岗位",
            "chip": "投递",
            "link": "#/opportunities",
            "cta": "去投递",
        })
    tasks.append({
        "key": "quiz",
        "title": "笔试备战模块规划中，先去题库熟悉真题",
        "chip": "笔试",
        "link": "#/interview",
        "cta": "去刷题",
    })
    return tasks[:4]


def dashboard(store: Dict) -> Dict:
    applications = store.get("applications", [])
    progress = progress_steps(store)
    highest = max(
        (status_index(app.get("status", "已投递")) for app in applications),
        default=-1,
    )
    sorted_apps = sorted(
        applications,
        key=lambda app: app.get("applied_at", ""),
        reverse=True,
    )
    return {
        "profile": store.get("profile"),
        "has_resume": store.get("resume") is not None,
        "resume_skills": extract_skills(store.get("resume")) if store.get("resume") else [],
        "progress": progress,
        "tasks": build_tasks(store),
        "recommended": recommendation_items(store, limit=3),
        "recent_applications": [
            application_view(store, app) for app in sorted_apps[:5]
        ],
        "stats": {
            "applications": len(applications),
            "offers": sum(1 for app in applications if status_index(app.get("status", "")) >= 4),
            "in_interview": sum(1 for app in applications if status_index(app.get("status", "")) >= 3),
        },
        "industries": INDUSTRIES,
    }
