"""简历文件解析：把 .txt / .docx / .pdf 转成可编辑的结构化简历。"""

import io
import re
from typing import Dict, List

SUPPORTED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf"}

_SECTION_RULES = [
    ("basic", r"基本信息|个人资料|个人信息|基本资料"),
    ("objective", r"求职意向|应聘岗位|期望岗位|期望职位|目标岗位|意向岗位"),
    ("profile", r"自我评价|个人简介|个人总结|个人概述|自我介绍|自我描述"),
    ("education", r"教育经历|教育背景|教育情况|学历背景|学习经历|教育"),
    ("project", r"项目经历|项目经验|项目实践|科研项目|课程项目|项目"),
    ("intern", r"实习经历|实习经验|工作经历|工作经验|社会实践|实习"),
    ("honor", r"荣誉奖项|获奖经历|获奖情况|所获荣誉|个人荣誉|奖项"),
    ("skill", r"专业技能|个人技能|技能清单|技能证书|资格证书|专业能力|综合能力|其他能力|技能"),
]

_HEADING_LINE = re.compile(
    r"^(?:[一二三四五六七八九十\d、.\-]+\s*)?"
    r"(?:教育经历|教育背景|教育情况|学习经历|教育|项目经历|项目经验|项目实践|科研项目|"
    r"课程项目|项目|实习经历|实习经验|工作经历|工作经验|社会实践|实习|专业技能|个人技能|"
    r"技能清单|技能证书|资格证书|专业能力|综合能力|其他能力|技能|荣誉奖项|获奖经历|获奖情况|所获荣誉|个人荣誉|奖项|求职意向|应聘岗位|期望岗位|期望职位|"
    r"目标岗位|意向岗位|自我评价|个人简介|个人总结|个人概述|自我介绍|自我描述|"
    r"基本信息|个人资料|个人信息|基本资料)\s*[:：]?$"
)

_PHONE = re.compile(r"(?<!\d)(?:86[- ]?)?1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PERIOD = re.compile(
    r"((?:19|20)\d{2}(?:\s*[./年]\s*\d{1,2}\s*[./月]?)?)"
    r"\s*(?:-|~|至|到|—)\s*"
    r"((?:19|20)\d{2}(?:\s*[./年]\s*\d{1,2}\s*[./月]?)?|至今|现在)"
)
_CITY_WORDS = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "武汉", "成都",
    "重庆", "西安", "长沙", "郑州", "合肥", "厦门", "天津", "青岛", "济南",
]
_INDUSTRY_WORDS = ["互联网", "金融", "快消", "制造", "咨询", "央国企", "新能源", "电商"]


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").replace("\u3000", " ")).strip()


def _heading_rest(line: str) -> str:
    parts = re.split(r"[:：]\s*", line, maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def extract_text(filename: str, data: bytes) -> str:
    """按扩展名抽取文件文本。"""
    ext = filename.lower()
    if ext.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(_clean_line(p.text) for p in doc.paragraphs if _clean_line(p.text))

    if ext.endswith(".pdf"):
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(_clean_line(line) for line in "\n".join(pages).splitlines() if _clean_line(line))

    text = data.decode("utf-8", errors="replace")
    if "\ufffd" in text:
        try:
            text = data.decode("gb18030")
        except UnicodeDecodeError:
            pass
    return "\n".join(_clean_line(line) for line in text.splitlines() if _clean_line(line))


def _field_before_colon(line: str, names: List[str]) -> str:
    prefix = "|".join(re.escape(name) for name in names)
    match = re.search(
        r"(?:^|(?<=[\s，,；;]))(?:" + prefix + r")\s*[:：]?\s*(.*?)\s*$",
        line,
    )
    return match.group(1) if match else ""


def _split_values(text: str) -> List[str]:
    """把技能/证书文本按常见分隔符切成标签。"""
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"[,，、;；|｜]", text)
    values = []
    for part in parts:
        value = part.strip()
        if not value:
            continue
        if len(value) > 24:
            value = re.split(r"(?<=[\w\u4e00-\u9fa5])(?=[A-Z][a-z]+)", value)[0]
        if len(value) <= 24:
            values.append(value)
    return values[:30]


def _text_blocks(lines: List[str]) -> List[List[str]]:
    blocks: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _looks_like_school(value: str) -> bool:
    return any(k in value for k in ["大学", "学院", "学校", "中学", "研究院"])


def _sectionize(lines: List[str]):
    """按标题切分简历文本，返回 文本段 -> 分类。"""
    sections = []
    current = []
    current_kind = "unknown"

    def heading_kind(line: str):
        if _HEADING_LINE.match(line):
            for kind, pattern in _SECTION_RULES:
                if re.search(pattern, line):
                    return kind
        numbered = re.match(r"^(?:[一二三四五六七八九十\d]+)[、.．]\s*(.*)$", line)
        candidate = numbered.group(1).strip() if numbered else line
        if candidate and len(candidate) <= 12 and re.search(r"经历|背景|简介|评价|技能|能力|奖项|意向|信息", candidate):
            for kind, pattern in _SECTION_RULES:
                if re.search(pattern, candidate):
                    return kind
        inline = re.match(
            r"^(?:[一二三四五六七八九十\d]+[、.．]\s*)?([\u4e00-\u9fa5A-Za-z]{2,12}?)\s*[:：]",
            line,
        )
        if inline:
            label = inline.group(1)
            for kind, pattern in _SECTION_RULES:
                if re.search(pattern, label):
                    return kind
        return None

    for raw in lines:
        line = _clean_line(raw)
        if not line:
            continue
        lower = line.lower()
        matched = heading_kind(line)
        if matched and (":" in line or "：" in line):
            if current:
                sections.append((current_kind, current))
            rest = _heading_rest(line)
            current = [rest] if rest else []
            current_kind = matched
            continue
        if lower.startswith("姓名") or lower.startswith("电话") or \
           lower.startswith("手机") or lower.startswith("邮箱") or \
           lower.startswith("email") or "男" in line[:12] or "女" in line[:12]:
            sections.append((current_kind, current))
            sections.append(("basic", [line]))
            current = []
            current_kind = "unknown"
            continue
        if matched:
            if current:
                sections.append((current_kind, current))
            current = [line]
            current_kind = matched
            continue
        current.append(line)
    if current:
        sections.append((current_kind, current))
    return [(kind, lines) for kind, lines in sections if lines]


def _clean_record(value: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _clean_multiline(value: str, limit: int = 3000) -> str:
    lines = []
    for raw in str(value or "").splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)[:limit]


def _strip_bullet(value: str) -> str:
    return re.sub(r"^[\s•·●○▪\-—]+", "", value or "").strip()


def _parse_education(block_lines: List[str]) -> List[Dict]:
    records = []
    groups: List[List[str]] = []
    current: List[str] = []
    for raw in block_lines:
        line = _clean_line(raw)
        if not line:
            continue
        if _looks_like_school(line):
            if current:
                groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)

    for block in groups:
        text = _clean_line(block[0])
        if not any(k in text for k in ["大学", "学院", "学校", "研究院", "中学"]) and not _PERIOD.search(text):
            continue
        item = {"school": "", "major": "", "degree": "", "period": "", "highlights": ""}
        period = _PERIOD.search(text)
        if period:
            item["period"] = re.sub(r"\s+", "", period.group(0))
            text = text.replace(period.group(0), " ")
        degree_match = re.search(r"(本科|硕士|博士|大专|专科|双学士)", text)
        if degree_match:
            item["degree"] = degree_match.group(1)
            text = text.replace(degree_match.group(1), " ")
        school_match = re.search(
            r"([\u4e00-\u9fa5A-Za-z0-9·（）()]{2,30}(?:大学|学院|学校|研究院|中学))",
            text,
        )
        if school_match:
            item["school"] = school_match.group(1)
            text = text.replace(item["school"], " ")
        parts = [p for p in re.split(r"[|｜,，;；\s]+", text) if p and not re.match(r"^[:：\-—~]+$", p)]
        if not item["major"] and parts:
            major_candidate = parts[0].strip("（()）")
            if len(major_candidate) <= 30:
                item["major"] = major_candidate
        if len(block) > 1:
            item["highlights"] = _clean_multiline("\n".join(block[1:]), 1500)
        if item["school"] or item["period"]:
            records.append({
                k: (_clean_multiline(v, 1500) if k == "highlights" else _clean_record(v, 80))
                for k, v in item.items()
            })
    return records[:4]


def _project_title(line: str) -> bool:
    parts = line.split("|")
    if len(parts) >= 3 and len(parts[0].strip()) <= 100:
        return True
    return line.startswith("《") and "|" in line


def _project_groups(block_lines: List[str]) -> List[List[str]]:
    groups: List[List[str]] = []
    current: List[str] = []
    for raw in block_lines:
        line = _clean_line(raw)
        if not line:
            if current:
                groups.append(current)
                current = []
            continue
        if _project_title(line):
            if current:
                groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)
    return groups


def _parse_project_group(block: List[str]) -> Dict:
    title = block[0].strip(":：.。，, |｜")
    parts = [part.strip(" |｜:：.。") for part in title.split("|")]
    item = {"name": parts[0], "subtitle": "", "period": "", "description": "", "achievement": ""}
    item["name"] = re.sub(r"\s+([》」)）])", r"\1", item["name"])
    item["name"] = re.sub(r"([《「(（])\s+", r"\1", item["name"])
    if len(parts) > 1:
        item["subtitle"] = " | ".join(part for part in parts[1:] if part)
    period = _PERIOD.search(title)
    if period:
        item["period"] = re.sub(r"\s+", "", period.group(0))
        item["name"] = item["name"].replace(period.group(0).strip(), "").strip(" -—")
    if not item["name"]:
        item["name"] = "未命名项目"

    mode = None
    content_lines = []
    harvest_lines = []
    for raw in block[1:]:
        line = _strip_bullet(raw)
        if not line:
            continue
        lower = line
        if lower.startswith("项目内容") or lower.startswith("项目简介"):
            mode = "content"
            rest = re.sub(r"^项目(?:内容|简介)\s*[:：]?\s*", "", line)
            if rest:
                content_lines.append(rest)
        elif lower.startswith("项目收获") or lower.startswith("项目成果"):
            mode = "harvest"
            rest = re.sub(r"^项目(?:收获|成果)\s*[:：]?\s*", "", line)
            if rest:
                harvest_lines.append(rest)
        elif mode == "content":
            content_lines.append(line)
        elif mode == "harvest":
            harvest_lines.append(line)
        else:
            content_lines.append(line)
    item["description"] = _clean_multiline("\n".join(content_lines), 3000)
    item["achievement"] = _clean_multiline("\n".join(harvest_lines), 2500)
    return item


def _parse_intern_group(block: List[str], text: str) -> Dict:
    item = {}
    period = _PERIOD.search(text)
    if period:
        item["period"] = re.sub(r"\s+", "", period.group(0))
    period_in_first = _PERIOD.search(block[0])
    period_text = period_in_first.group(0).strip() if period_in_first else ""
    first = re.sub(re.escape(period_text), "", block[0]).strip(":：.。，, -—")
    text_body = _clean_multiline("\n".join(block[1:]), 2000)
    if not block[1:]:
        text_body = ""
    role_match = re.search(r"(?:岗位|职位|担任)\s*[:：]\s*([\u4e00-\u9fa5A-Za-z0-9/（）()·-]{1,30})", text)
    role = role_match.group(1) if role_match else ""
    company = ""
    known_company = re.search(
        r"([\u4e00-\u9fa5A-Za-z0-9·]{2,24}(?:事务所|公司|集团|银行|证券|保险|科技|研究院|学校|医院))",
        first,
    )
    if known_company:
        company = known_company.group(1)
        leftover = first.replace(company, "", 1).strip(" |｜-—")
        if leftover and not role and not leftover.startswith(("202", "19")):
            role = leftover
    else:
        tokens = [token for token in re.split(r"[\s|｜/]+", first) if token]
        if tokens:
            company = tokens[0]
            if len(tokens) > 1 and re.search(r"(实习|专员|助理|工程师|分析师|经理|顾问|实习生)", tokens[1]):
                if not role:
                    role = tokens[1]
    if len(company) <= 2 and company in ["无", "暂无", "待定"]:
        company = ""
    item["company"] = _clean_record(company, 60)
    item["role"] = _clean_record(role, 50)
    item["description"] = text_body
    return item


def _parse_experience(block_lines: List[str], kind: str) -> List[Dict]:
    """解析项目/实习内容：项目按「标题 | 赛事 | 角色」分行，实习按空行分块。"""
    if kind == "project":
        groups = _project_groups(block_lines)
        return [_parse_project_group(group) for group in groups if group][:4]
    records = []
    for block in _text_blocks(block_lines):
        text = " ".join(_clean_line(x) for x in block)
        if not text or len(text) < 2:
            continue
        records.append(_parse_intern_group(block, text))
    return records[:4]


def parse_resume_text(text: str, source_name: str = "") -> Dict:
    """把纯文本解析为前端可回填的简历结构。"""
    lines = [_clean_line(line) for line in text.splitlines()]
    resume = {
        "full_name": "",
        "phone": "",
        "email": "",
        "wechat": "",
        "target_role": "",
        "target_direction": "",
        "target_industry": "",
        "target_city": "",
        "self_intro": "",
        "education": [],
        "projects": [],
        "internships": [],
        "honors": [],
        "skills": [],
    }
    warnings = []
    for line in lines:
        for label, key in [("姓名", "full_name"), ("电话", "phone"), ("手机", "phone"),
                           ("邮箱", "email"), ("微信", "wechat"), ("WeChat", "wechat")]:
            if line.lower().startswith(label.lower()) or re.match(rf"^{label}\s*[:：]", line):
                value = _field_before_colon(line, [label])
                if value and not resume[key]:
                    resume[key] = value[:60]
    if not resume["full_name"]:
        name_match = re.search(
            r"^([\u4e00-\u9fa5·]{2,6})\s*(?:男|女|同学)?\s*$",
            lines[0] if lines else "",
        )
        if name_match and "教育" not in name_match.group(1) and "简历" not in name_match.group(1):
            resume["full_name"] = name_match.group(1)
    phone = _PHONE.search(text)
    if phone:
        resume["phone"] = phone.group(0)
    email = _EMAIL.search(text)
    if email:
        resume["email"] = email.group(0)

    sections = _sectionize(lines)
    for kind, section_lines in sections:
        body_lines = [
            _strip_bullet(line)
            for line in section_lines
            if not _HEADING_LINE.match(line)
        ]
        if kind == "objective":
            for line in body_lines:
                value = _field_before_colon(line, ["求职意向", "应聘岗位", "期望岗位", "期望职位", "目标岗位", "意向岗位"])
                if value and not resume["target_role"]:
                    resume["target_role"] = value.strip("（）()[]【】 ")[:80]
                elif line and not resume["target_role"] and "：" not in line and ":" not in line \
                        and len(line) <= 80 and not re.search(r"(大学|学院|技能|经验|项目)", line):
                    pieces = re.split(r"[|｜/，,]+", line)
                    role_candidate = pieces[0].strip()
                    if role_candidate:
                        resume["target_role"] = role_candidate[:80]
                    for piece in pieces:
                        piece = piece.strip()
                        if piece in _CITY_WORDS:
                            resume["target_city"] = piece
                        elif piece in _INDUSTRY_WORDS:
                            resume["target_industry"] = piece
                for label, city_key in [("期望城市", "target_city"), ("意向城市", "target_city"),
                                        ("工作城市", "target_city"), ("目标城市", "target_city")]:
                    city = _field_before_colon(line, [label])
                    if city:
                        resume["target_city"] = city[:30]
        elif kind == "profile":
            resume["self_intro"] = _clean_record("；".join(body_lines), 600)
        elif kind == "education":
            resume["education"].extend(_parse_education(body_lines))
        elif kind == "project":
            resume["projects"].extend(_parse_experience(body_lines, "project"))
        elif kind == "intern":
            resume["internships"].extend(_parse_experience(body_lines, "intern"))
        elif kind == "honor":
            for raw in body_lines:
                line = raw.strip("：: .。")
                if not line or len(line) < 4:
                    continue
                if re.match(r"^[\d一二三四五六七八九十]+\s*[:：]?\s*(荣誉|奖项|获奖|综合|技能)", line):
                    continue
                resume["honors"].append(line[:120])
        elif kind == "skill":
            skill_texts = []
            for line in body_lines:
                for label in ["专业技能", "个人技能", "技能证书", "技能"]:
                    if label in line:
                        line = re.split(rf"^{label}\s*[:：]", line, maxsplit=1)[-1]
                        break
                if line and line not in {"综合能力", "其他能力", "专业能力", "技能"}:
                    skill_texts.append(line)
            for value in _split_values(" ".join(skill_texts)):
                if value not in resume["skills"]:
                    resume["skills"].append(value)

    for keyword, direction in [("后端", "后端"), ("前端", "前端"), ("算法", "算法"),
                               ("数据分析", "数据"), ("产品", "产品"), ("运营", "运营"),
                               ("市场", "市场"), ("咨询", "咨询")]:
        if keyword in resume["target_role"]:
            resume["target_direction"] = direction
            break
    for industry in ["互联网", "金融", "快消", "制造", "咨询", "央国企"]:
        if industry in (resume["target_role"] + resume["target_industry"]):
            resume["target_industry"] = industry
            break
    if not resume["target_city"]:
        for line in lines:
            if "城市" in line or "地点" in line:
                value = _field_before_colon(line, ["期望城市", "意向城市", "工作城市", "目标城市", "期望工作地点"])
                if value:
                    resume["target_city"] = value[:30]
                    break
    if resume["phone"] and not re.search(r"1[3-9]\d{9}", resume["phone"]):
        resume["phone"] = ""
    if len(resume["self_intro"]) < 4:
        resume["self_intro"] = ""
    resume["education"] = resume["education"][:4]
    resume["projects"] = resume["projects"][:4]
    resume["internships"] = resume["internships"][:4]
    resume["honors"] = list(dict.fromkeys(resume["honors"]))[:12]
    award_markers = "奖学金|三好|优秀|竞赛奖|比赛奖|获奖|一等奖|二等奖|三等奖|荣誉|称号"
    for raw in lines:
        line = _strip_bullet(raw)
        if not line or line in resume["honors"]:
            continue
        if re.match(r"^(?:19|20)\d{2}\s*[./]?\s*\d{0,2}", line) and re.search(award_markers, line):
            resume["honors"].append(line[:120])
    resume["honors"] = list(dict.fromkeys(resume["honors"]))[:12]
    resume["skills"] = resume["skills"][:30]

    if not resume["education"]:
        warnings.append("未识别到教育经历，请手动补充学校与专业")
    if not resume["projects"] and not resume["internships"]:
        warnings.append("未识别到项目或实习经历，可先查看解析文本后手动拆分")
    if not resume["skills"]:
        warnings.append("未识别到技能标签，建议在解析结果中手动补充")
    return {"resume": resume, "warnings": warnings, "preview": text[:3000]}


def parse_resume_file(filename: str, data: bytes) -> Dict:
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError("暂只支持 .txt / .md / .docx / .pdf 格式")
    text = extract_text(filename, data)
    if not text.strip():
        raise ValueError("未能从文件中提取到文字，请确认文件可正常复制文本")
    return parse_resume_text(text, filename)
