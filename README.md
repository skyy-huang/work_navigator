# 职航 · 实习就业智能助手 (Zhihang)

面向大学生实习就业的智能辅助系统（由「双创智能教练」重构而来）。

当前处于 **v0.2 最小可用 Demo**：打通了「简历创建 → 岗位智能匹配 → 一键投递」主链路。

---

## 快速启动

```bash
python -m uvicorn main:app --reload --port 8120
```

访问 http://localhost:8120

> 说明：演示数据为**单用户（李同学）**，暂不含登录/权限；`--reload` 开启后修改代码会自动生效。

---

## 当前功能（已实现）

- 工作台：求职进度六步（意向/简历/投递/笔试/面试/Offer）、动态今日任务、为你推荐、我的投递（演示推进状态）
- 简历：结构化创建/编辑（求职意向、教育、技能标签、项目、实习），文本自动识别技能
- 机会速览：示例岗位库（互联网优先 + 金融/快消/制造/咨询），行业筛选与关键词搜索
- 智能匹配：按「技能重合 62% + 方向 22% + 行业 10% + 城市 6%」确定性打分，展示命中与缺口技能
- 一键投递：投递记录、撤回、演示状态推进（正式版将由笔试/面试模块驱动）
- 页面框架：明亮学院风 SPA，AI 求职助手与面试题库为占位视图

## 规划中

- **笔试备战**（核心模块，方案待讨论）：题库、在线笔试、AI 解析
- AI 求职助手：简历诊断/改写、模拟面试、真题解析
- 校园合作：企业/就业办管理端、校园内推岗位
- 登录与多用户、简历文件上传解析、简历导出 PDF

## 项目结构

```
├── main.py                 # FastAPI：REST API + 页面托管
├── jobflow/                # 新业务域（v0.2）
│   ├── seed.py             #   默认档案 + 示例岗位库
│   ├── store.py            #   JSON 文件持久化
│   ├── matching.py         #   技能提取 + 岗位匹配引擎
│   └── service.py          #   进度/任务/投递聚合服务
├── frontend/
│   ├── index.html          # 职航 SPA
│   └── static/
│       ├── css/app.css     # 明亮学院风样式
│       └── js/app.js       # 路由 + 前端交互
└── data/jobflow_store.json # 运行时数据（简历/投递记录）
```

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/me` | 当前档案 + 简历 + 识别技能 |
| PUT | `/api/resume` | 创建/更新简历 |
| GET | `/api/jobs?industry=&q=` | 岗位列表（带匹配分） |
| GET | `/api/recommendations` | 按简历排序的推荐岗位 |
| POST | `/api/applications` | 投递岗位 |
| GET | `/api/applications` | 投递记录 |
| POST | `/api/applications/{id}/advance` | 演示状态推进 |
| DELETE | `/api/applications/{id}` | 撤回投递 |
| GET | `/api/dashboard` | 工作台聚合数据 |

## 重构说明

- 教师端（看板页、`teacher/`、教师登录）与双创教练业务接口已删除。
- 旧引擎目录（`graph/`、`hypergraph/`、`prompts/`、`rag/`、`scripts/`、`test_coach.py`）与旧创业案例数据（`data/cases`）已不被引用，待确认后统一清理归档。
