"""
职航 · 实习就业智能助手 —— FastAPI 主程序

启动命令：uvicorn main:app --reload --port 8120
"""

import os
from typing import List, Optional
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from jobflow.ai_resume import polish_resume
from jobflow.assistant.advisor import advise
from jobflow.matching import extract_skills
from jobflow.resume_docs import resume_to_docx, resume_to_pdf
from jobflow.resume_parser import parse_resume_file
from jobflow.service import (
    advance_application,
    application_view,
    create_application,
    dashboard,
    jobs_list,
    recommendation_items,
    remove_application,
)
from jobflow.store import load_store, save_store

app = FastAPI(title="职航 · 实习就业智能助手", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 单一演示学生档案的持久化仓库（后续接入多用户与登录后再扩展）
store = load_store()


# ─────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────
class ResumeIn(BaseModel):
    full_name: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    target_role: str = ""
    target_direction: str = ""
    target_industry: str = ""
    target_city: str = ""
    self_intro: str = ""
    education: List[dict] = []
    projects: List[dict] = []
    internships: List[dict] = []
    honors: List[str] = []
    skills: List[str] = []


class ApplyIn(BaseModel):
    job_id: str


class ExportIn(BaseModel):
    format: str = "docx"
    resume: ResumeIn


class ChatIn(BaseModel):
    message: str


def _clean_text(value: Optional[str], limit: int = 2000) -> str:
    return (value or "").strip()[:limit]


def _clean_list(items) -> List[str]:
    return [str(item).strip()[:40] for item in (items or []) if str(item).strip()]


def _clean_honors(items) -> List[str]:
    return [str(item).strip()[:120] for item in (items or []) if str(item).strip()][:12]


def _clean_blocks(blocks) -> List[dict]:
    out = []
    for block in blocks or []:
        item = {
            key: _clean_text(
                block.get(key),
                2000 if key in ("description", "achievement", "achievements", "highlights") else 200,
            )
            for key in block.keys()
        }
        if any(item.values()):
            out.append(item)
    return out


def _resume_dict(payload: ResumeIn) -> dict:
    return {
        "full_name": _clean_text(payload.full_name, 40),
        "phone": _clean_text(payload.phone, 30),
        "email": _clean_text(payload.email, 80),
        "wechat": _clean_text(payload.wechat, 40),
        "target_role": _clean_text(payload.target_role, 80),
        "target_direction": _clean_text(payload.target_direction, 40),
        "target_industry": _clean_text(payload.target_industry, 40),
        "target_city": _clean_text(payload.target_city, 40),
        "self_intro": _clean_text(payload.self_intro, 800),
        "education": _clean_blocks(payload.education)[:4],
        "projects": _clean_blocks(payload.projects)[:4],
        "internships": _clean_blocks(payload.internships)[:4],
        "honors": _clean_honors(payload.honors),
        "skills": _clean_list(payload.skills)[:30],
    }


# ─────────────────────────────────────────────
# API：学生档案与简历
# ─────────────────────────────────────────────
@app.get("/api/me")
async def get_me():
    """当前演示学生档案：基本信息 + 简历 + 已识别技能。"""
    resume = store.get("resume")
    return {
        "profile": store.get("profile"),
        "has_resume": resume is not None,
        "resume": resume,
        "resume_skills": extract_skills(resume) if resume else [],
    }


@app.put("/api/resume")
async def put_resume(payload: ResumeIn):
    """创建 / 更新简历。简历创建后会即时驱动岗位匹配。"""
    has_content = any([
        payload.target_role.strip(),
        payload.self_intro.strip(),
        payload.education,
        payload.projects,
        payload.internships,
    ])
    if not has_content:
        raise HTTPException(status_code=400, detail="请至少填写求职意向或一段经历")

    resume = _resume_dict(payload)
    profile = store.setdefault("profile", {})
    if resume["full_name"]:
        profile["name"] = resume["full_name"]
    if resume["education"]:
        first_education = resume["education"][0]
        if first_education.get("school"):
            profile["school"] = first_education["school"]
        if first_education.get("major"):
            profile["major"] = first_education["major"]
    store["resume"] = resume
    save_store(store)
    return {
        "resume": resume,
        "resume_skills": extract_skills(resume),
        "message": "简历已保存",
    }


@app.post("/api/resume/parse")
async def parse_uploaded_resume(file: UploadFile = File(...)):
    """上传并解析 .txt / .docx / .pdf 简历，返回可回填结构。"""
    filename = file.filename or "resume.txt"
    data = await file.read(8 * 1024 * 1024)
    try:
        result = parse_resume_file(filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "filename": filename,
        "preview": result["preview"],
        "warnings": result["warnings"],
        "resume": result["resume"],
    }


@app.post("/api/resume/polish")
async def polish_resume_endpoint(payload: ResumeIn):
    """生成简历润色建议：DeepSeek 不可用时自动降级到离线引擎。"""
    resume = _resume_dict(payload)
    if not any([
        resume["self_intro"],
        resume["projects"],
        resume["internships"],
    ]):
        raise HTTPException(status_code=400, detail="请先补充自我介绍或项目 / 实习描述，再进行 AI 润色")
    return polish_resume(resume)


@app.post("/api/resume/export")
async def export_resume_endpoint(payload: ExportIn):
    """把当前编辑中的简历导出为 Word / PDF（无需先保存到服务器）。"""
    resume = _resume_dict(payload.resume)
    has_content = any([
        resume["target_role"],
        resume["self_intro"],
        resume["education"],
        resume["projects"],
        resume["internships"],
    ])
    if not has_content:
        raise HTTPException(status_code=400, detail="请先填写简历内容，再导出")
    output_format = (payload.format or "docx").lower()
    if output_format == "docx":
        try:
            content = resume_to_docx(resume, store.get("profile"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Word 导出失败：" + str(exc))
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = ".docx"
    elif output_format == "pdf":
        try:
            content = resume_to_pdf(resume, store.get("profile"))
        except RuntimeError as exc:
            raise HTTPException(status_code=501, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail="PDF 导出失败：" + str(exc))
        media_type = "application/pdf"
        ext = ".pdf"
    else:
        raise HTTPException(status_code=400, detail="导出格式仅支持 docx 或 pdf")
    name = resume.get("full_name") or (store.get("profile") or {}).get("name") or "我的简历"
    role = resume.get("target_role") or "求职"
    filename = f"{name}-{role}-简历{ext}"
    disposition = "attachment; filename*=UTF-8''" + quote(filename)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


# ─────────────────────────────────────────────
# API：AI 求职助手（回答顾问）
# ─────────────────────────────────────────────
@app.post("/api/assistant/chat")
async def assistant_chat(payload: ChatIn):
    """回答顾问：先检索知识库与个人数据，再返回本地可溯源答案。"""
    return advise(store, payload.message)


# ─────────────────────────────────────────────
# API：岗位与智能匹配
# ─────────────────────────────────────────────
@app.get("/api/jobs")
async def get_jobs(
    industry: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
):
    """岗位列表，附带基于当前简历的匹配分与技能差（无简历时 match 为 null）。"""
    query = (q or "").strip()
    return {
        "jobs": jobs_list(store, industry=industry or "", query=query or None),
        "industries": ["全部"] + dashboard(store).get("industries", []),
    }


@app.get("/api/recommendations")
async def get_recommendations(limit: int = Query(default=4, le=8)):
    """按当前简历匹配度排序的推荐岗位。"""
    if not store.get("resume"):
        raise HTTPException(status_code=400, detail="请先创建简历，再开启智能匹配")
    return {"items": recommendation_items(store, limit=limit)}


# ─────────────────────────────────────────────
# API：投递记录（演示状态流转）
# ─────────────────────────────────────────────
@app.post("/api/applications")
async def apply(payload: ApplyIn):
    if not store.get("resume"):
        raise HTTPException(status_code=400, detail="请先创建简历再投递岗位")
    if not any(job["id"] == payload.job_id for job in store["jobs"]):
        raise HTTPException(status_code=404, detail="岗位不存在")
    application = create_application(store, payload.job_id)
    if application is None:
        raise HTTPException(status_code=409, detail="该岗位已投递，请勿重复申请")
    save_store(store)
    return application_view(store, application)


@app.get("/api/applications")
async def get_applications():
    return {
        "applications": [
            application_view(store, app)
            for app in sorted(
                store.get("applications", []),
                key=lambda app: app.get("applied_at", ""),
                reverse=True,
            )
        ]
    }


@app.post("/api/applications/{application_id}/advance")
async def advance(application_id: str):
    """演示用：手动推进投递状态（正式版将由笔试/面试模块驱动）。"""
    application = advance_application(store, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    save_store(store)
    return application_view(store, application)


@app.delete("/api/applications/{application_id}")
async def withdraw(application_id: str):
    if not remove_application(store, application_id):
        raise HTTPException(status_code=404, detail="投递记录不存在")
    save_store(store)
    return {"message": "已撤回投递"}


# ─────────────────────────────────────────────
# API：工作台聚合
# ─────────────────────────────────────────────
@app.get("/api/dashboard")
async def get_dashboard():
    """工作台聚合数据：进度、任务、推荐与最近投递。"""
    return dashboard(store)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "zhihang"}


# ─────────────────────────────────────────────
# 页面与静态资源
# ─────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse("frontend/index.html")


app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8120, reload=True)
