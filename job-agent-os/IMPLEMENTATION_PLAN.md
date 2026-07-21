# Job Agent OS — 完整实现规划

> **本文档是项目实现的唯一指导文件。每次打开新窗口时，先阅读本文档恢复上下文，再确认当前进度和下一步任务。**

---

## 项目概述

### 这是什么项目？

**Job Agent OS** 是一个基于 Multi-Agent 架构的智能求职系统，面向秋招应届生。用户只需用自然语言描述求职意向（如"河南省、国企、计算机、Java方向"），系统即可自动完成：搜索岗位 → 解析 JD → 匹配简历 → 推荐排序 → 优化简历 → 生成面试题 → 管理投递状态，全流程由多个 AI Agent 协作完成，关键节点支持人工审批（Human-in-the-Loop）。

### 项目目标

这不是一个 Demo，而是一个**可以写进简历、用于面试展示的工程化项目**，需要体现：
- Multi-Agent 协作设计能力
- LangGraph 编排与状态管理
- Harness Engineering（可观测性、护栏、评估）
- 完整的工程化实践（类型安全、测试、CI/CD、Docker）

### 技术栈

| 层面 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| Web 框架 | FastAPI + Uvicorn |
| Agent 框架 | LangGraph + LangChain |
| LLM | deepseek-v4-pro（主力）/ deepseek-v4-flash（降级） |
| 数据校验 | Pydantic v2 + pydantic-settings |
| ORM | SQLAlchemy 2.0 (async) + asyncpg |
| 数据库 | PostgreSQL 16 + pgvector |
| 缓存 | Redis 7 |
| 迁移 | Alembic |
| 依赖管理 | uv + pyproject.toml (PEP 621) |
| 容器化 | Docker + docker-compose |
| 可观测性 | Langfuse + OpenTelemetry |
| 测试 | pytest + pytest-asyncio |
| Lint | ruff + mypy (strict) |

### 系统架构（分层）

```
┌─────────────────────────────────────────────────────────┐
│                    接入层 (api/)                          │
│         FastAPI REST + WebSocket + JWT 认证              │
├─────────────────────────────────────────────────────────┤
│                    业务层 (services/)                     │
│         业务逻辑编排，连接 API 与底层能力                  │
├─────────────────────────────────────────────────────────┤
│                    编排层 (graph/)                        │
│         LangGraph StateGraph + 条件路由 + Checkpointer    │
├─────────────────────────────────────────────────────────┤
│                    Agent 层 (agents/)                    │
│    Intent / Search / Parse / Match / Resume / Interview  │
├─────────────────────────────────────────────────────────┤
│                    Tool 层 (tools/)                      │
│         搜索适配器 / 解析器 / 匹配器 / 导出器             │
├─────────────────────────────────────────────────────────┤
│                    Memory 层 (memory/)                   │
│         MemoryStore + RAG Pipeline + VectorStore         │
├─────────────────────────────────────────────────────────┤
│                    Harness 层 (harness/)                 │
│    Trace / GuardRails / Budget / Recovery / HITL / Eval  │
├─────────────────────────────────────────────────────────┤
│                    持久层 (db/ + models/)                 │
│         PostgreSQL + Redis + Alembic 迁移                │
└─────────────────────────────────────────────────────────┘
```

### Agent 协作流程（主 DAG）

```
用户输入 → [Intent Agent] → 需要澄清? → [Human: 补充信息] → 回到 Intent
                ↓ 不需要
         [Search Agent] → 并行搜索多平台
                ↓
         [Parse Agent] → 批量结构化 JD
                ↓
         [Match Agent] → 匹配评分 + 排序
                ↓
         [Human: 确认推荐] → 拒绝? → 回到 Match
                ↓ 接受
         [Resume Agent] → 优化简历
                ↓
         [Human: 审批简历] → 打回? → 回到 Resume
                ↓ 通过
         [Interview Agent] → 生成面试题
                ↓
         [Tracker Agent] → 创建投递记录 → 完成
```

### 项目目录结构

```
job-agent-os/
├── pyproject.toml              # 项目配置 + 依赖 (PEP 621)
├── .python-version             # Python 3.12
├── .env.example                # 环境变量模板
├── Dockerfile                  # 多阶段构建
├── docker-compose.yml          # PostgreSQL + Redis + App
├── Makefile                    # make dev/test/lint/migrate
├── configs/settings.dev.yaml   # 开发环境配置
├── src/job_agent_os/
│   ├── main.py                 # FastAPI 入口 + lifespan
│   ├── settings.py             # Pydantic Settings 全局配置
│   ├── api/                    # REST API 层
│   │   ├── deps.py             # 依赖注入 (DB/Auth/分页)
│   │   ├── middleware.py       # 中间件 + 全局异常处理
│   │   ├── response.py         # 统一响应格式
│   │   └── v1/                 # 12 个路由模块
│   ├── models/                 # SQLAlchemy ORM (10张表)
│   │   └── base.py             # Base + UUIDMixin + TimestampMixin
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── db/                     # DB 连接 (session.py + redis.py)
│   ├── graph/                  # LangGraph 编排
│   │   ├── state.py            # JobAgentState (TypedDict)
│   │   ├── main_graph.py       # StateGraph 构建 + compile
│   │   ├── nodes.py            # Agent → Node 映射
│   │   ├── edges.py            # 条件路由函数
│   │   └── checkpointer.py     # MemorySaver / PostgresSaver
│   ├── agents/                 # 7 个 Agent
│   │   ├── base.py             # BaseAgent (ABC)
│   │   ├── intent_agent.py     # 意图解析
│   │   ├── search_agent.py     # 多平台搜索
│   │   ├── parse_agent.py      # JD 解析
│   │   ├── match_agent.py      # 匹配评分
│   │   ├── resume_agent.py     # 简历优化
│   │   ├── interview_agent.py  # 面试题生成
│   │   └── tracker_agent.py    # 投递管理
│   ├── tools/                  # Tool 层 (按领域分子目录)
│   │   ├── registry.py         # Tool 注册表
│   │   ├── search/             # 平台适配器 (boss/guopin/niuke)
│   │   ├── parse/              # HTML/PDF 解析 + JD 结构化
│   │   ├── match/              # Embedding + 规则 + 技能匹配
│   │   ├── resume/             # 简历解析 + 优化 + PDF 导出
│   │   └── interview/          # 技术题 + 行为题生成
│   ├── prompts/                # Prompt 模板管理
│   │   ├── loader.py           # YAML 加载 + Jinja2 渲染
│   │   └── templates/          # 按 Agent 分目录的 YAML 模板
│   ├── memory/                 # Memory + RAG
│   │   ├── store.py            # MemoryStore (Postgres)
│   │   ├── rag.py              # RAG Pipeline
│   │   ├── embeddings.py       # Embedding 服务
│   │   └── vectorstore.py      # pgvector 适配
│   ├── harness/                # Harness Runtime
│   │   ├── runtime.py          # 执行入口 (门面)
│   │   ├── trace_manager.py    # 全链路追踪
│   │   ├── guard_rails.py      # 护栏 (Token/步数/循环)
│   │   ├── budget_controller.py# Token 预算
│   │   ├── recovery_manager.py # 错误恢复
│   │   ├── hitl_gateway.py     # Human-in-the-Loop
│   │   └── eval/               # 评估框架
│   ├── services/               # 业务逻辑层
│   └── core/                   # 核心基础设施
│       ├── security.py         # JWT + bcrypt
│       ├── exceptions.py       # 异常体系
│       ├── error_codes.py      # 错误码枚举
│       ├── events.py           # 事件总线
│       └── utils.py            # 工具函数
└── tests/                      # 测试 (unit/integration/eval)
```

### 数据库设计（10张表）

| 表名 | 用途 |
|------|------|
| users | 用户信息 + 偏好 + Token 预算 |
| resumes | 简历（结构化数据 + Embedding） |
| jobs | 岗位（结构化 JD + Embedding） |
| applications | 投递记录 + 状态机 + 匹配报告 |
| agent_logs | Agent 执行日志（追踪） |
| prompt_versions | Prompt 版本管理 |
| tool_calls | Tool 调用记录 |
| human_approvals | 人工审批记录 |
| memories | 记忆（短期/长期/RAG chunk） |
| evaluations | 评估记录 |

### 关键设计决策

| 决策 | 选择                  | 理由 |
|------|---------------------|------|
| Agent 通信 | 共享 State（非消息传递）     | LangGraph 原生，支持回溯 |
| 编排模式 | 中心式 DAG（非自由对话）      | 可控性强，易加 HITL |
| HITL 实现 | interrupt_before + Checkpointer | LangGraph 原生机制 |
| 依赖管理 | uv + pyproject.toml | 极快 + PEP 621 标准 |
| 模型策略 | 分级调用（flash 简单/pro 复杂） | 控制成本 |
| 错误恢复 | Checkpoint 回滚 + 指数退避 | 不丢进度 |

### 如何运行

```bash
cd job-agent-os
cp .env.example .env          # 配置环境变量
make docker-up                # 启动 PostgreSQL + Redis
make migrate                  # 运行数据库迁移
make dev                      # 启动开发服务器 (localhost:8000)
make test                     # 运行测试
make lint                     # 代码检查
```

### API 认证

- 方式: Bearer Token (JWT HS256)
- Access Token: 30 分钟有效
- Refresh Token: 7 天有效
- Header: `Authorization: Bearer <token>`

### 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... },
  "meta": { "request_id": "uuid", "timestamp": "ISO8601" }
}
```

---

## 当前进度总览

| 阶段 | 状态 | 完成度 |
|------|------|--------|
| Phase 1: 工程骨架 | ✅ 完成 | 100% |
| Phase 2: 核心 API | ✅ 完成 | 100% |
| Phase 3: Agent 真实逻辑 | ✅ 完成 | 100% |
| Phase 4: Tool 层实现 | ✅ 完成 | 100% |
| Phase 5: Memory/RAG | ✅ 完成 | 100% |
| Phase 6: Harness Runtime | ✅ 完成 | 100% |
| Phase 7: 集成测试 | ✅ 完成 | 100% |

---

## Phase 2: 核心 API 补全

### Task 2.1: Jobs API + Service
- [x] 文件: `services/job_service.py`
- [x] 文件: `api/v1/jobs.py`
- [x] 功能:
  - POST /v1/jobs/search — 触发搜索（异步，返回 session_id）
  - GET /v1/jobs — 岗位列表（分页+过滤）
  - GET /v1/jobs/{id} — 岗位详情
  - POST /v1/jobs/manual — 手动录入 JD
- [x] 验收: 搜索触发后返回 session_id，岗位 CRUD 正常

### Task 2.2: Applications API + Service
- [x] 文件: `services/application_service.py`
- [x] 文件: `api/v1/applications.py`
- [x] 功能:
  - POST /v1/applications — 创建投递
  - GET /v1/applications — 投递列表
  - GET /v1/applications/kanban — 看板视图
  - GET /v1/applications/{id} — 投递详情
  - PATCH /v1/applications/{id}/status — 更新状态（状态机校验）
  - GET /v1/applications/statistics — 统计
- [x] 状态机: pending → applied → written_test → round1 → round2 → hr → offer/rejected
- [x] 验收: 非法状态流转返回 40501 错误码

### Task 2.3: Sessions API + Service
- [x] 文件: `services/session_service.py`
- [x] 文件: `api/v1/sessions.py`
- [x] 功能:
  - POST /v1/sessions — 创建会话（202 异步）
  - GET /v1/sessions — 会话列表
  - GET /v1/sessions/{id} — 会话状态
  - POST /v1/sessions/{id}/messages — 发送消息
  - POST /v1/sessions/{id}/cancel — 终止会话
  - GET /v1/sessions/{id}/logs — 执行日志
  - GET /v1/sessions/{id}/timeline — 时间线
  - GET /v1/sessions/{id}/recommendations — 推荐列表
  - POST /v1/sessions/{id}/recommendations/feedback — 推荐反馈
- [x] 核心: session_service 内部调用 HarnessRuntime.execute()
- [x] 验收: 创建会话 → 执行 → 获取结果 完整流程

### Task 2.4: Approvals API + Service
- [x] 文件: `services/approval_service.py`
- [x] 文件: `api/v1/approvals.py`
- [x] 功能:
  - GET /v1/approvals — 待审批列表
  - GET /v1/approvals/{id} — 审批详情
  - POST /v1/approvals/{id}/respond — 提交审批
  - POST /v1/approvals/batch-respond — 批量审批
- [x] 验收: 审批通过后 Graph 恢复执行

### Task 2.5: Interview API
- [x] 文件: `api/v1/interview.py`
- [x] 功能:
  - POST /v1/interview/questions — 生成面试题（异步）
  - GET /v1/interview/questions/{task_id} — 获取结果
- [x] 验收: 给定 job_id 生成技术题+行为题

### Task 2.6: Memory API
- [x] 文件: `api/v1/memory.py`
- [x] 功能:
  - GET /v1/memory — 记忆列表
  - PUT /v1/memory/{key} — 创建/更新记忆
  - DELETE /v1/memory/{id} — 删除记忆
  - POST /v1/memory/search — 语义搜索
- [x] 验收: 记忆 CRUD + 语义搜索正常

### Task 2.7: Monitoring + Evaluations API
- [x] 文件: `api/v1/monitoring.py`
- [x] 文件: `api/v1/evaluations.py`
- [x] 功能:
  - GET /v1/monitoring/health — 健康检查
  - GET /v1/monitoring/token-usage — Token 统计
  - GET /v1/evaluations/report — 评估报告
- [x] 验收: 返回正确的统计数据

---

## Phase 3: Agent 真实逻辑

### Task 3.1: 完善 Intent Agent
- [x] 文件: `agents/intent_agent.py`
- [x] 改进:
  - 使用 LangChain structured output (with_structured_output)
  - 支持多轮对话补全（从 state.messages 获取上下文）
  - 加载用户历史偏好（从 Memory）
- [x] 验收: "河南 国企 Java" → 正确结构化输出

### Task 3.2: 完善 Search Agent + 真实适配器
- [x] 文件: `tools/search/boss.py` — BOSS 直聘适配器
- [x] 文件: `tools/search/guopin.py` — 国聘适配器
- [x] 文件: `tools/search/niuke.py` — 牛客适配器
- [x] 文件: `tools/common/dedup.py` — 去重工具
- [x] 实现:
  - 使用 httpx + BeautifulSoup 爬取
  - 请求频率控制（rate_limit）
  - 单平台失败不阻塞（asyncio.gather + return_exceptions）
  - 基于 content_hash 去重
- [x] 验收: 并行搜索 3 平台，单平台超时不影响结果

### Task 3.3: 完善 Parse Agent + 解析工具
- [x] 文件: `tools/parse/html_parser.py`
- [x] 文件: `tools/parse/jd_structurer.py`
- [x] 文件: `prompts/templates/parse/structure_jd.yaml`
- [x] 实现:
  - BeautifulSoup 提取 HTML 正文
  - LLM 结构化 JD（with_structured_output → ParsedJD）
  - 批量并发解析（asyncio.Semaphore 限制并发）
  - confidence < 0.6 标记为失败
- [x] 验收: 给定 JD 文本输出完整 ParsedJD

### Task 3.4: 完善 Match Agent + 匹配工具
- [x] 文件: `tools/match/rule_filter.py`
- [x] 文件: `tools/match/skill_matcher.py`
- [x] 文件: `prompts/templates/match/score_and_rank.yaml`
- [x] 实现:
  - 硬性条件过滤（学历、地区）
  - 技能关键词匹配（精确 + 模糊）
  - LLM 综合评分 + 推荐理由生成
- [x] 验收: 给定简历 + 5 JD，输出排序结果 + 理由

### Task 3.5: 完善 Resume Agent + 简历工具
- [x] 文件: `tools/resume/keyword_optimizer.py`
- [x] 文件: `prompts/templates/resume/optimize_resume.yaml`
- [x] 实现:
  - LLM 优化措辞（约束：不捏造经历）
  - 生成修改对比（before/after/reason）
- [x] 验收: 输出修改对比，不捏造内容

### Task 3.6: 完善 Interview Agent + 面试题工具
- [x] 文件: `tools/interview/tech_question_gen.py`
- [x] 文件: `tools/interview/behavior_question_gen.py`
- [x] 文件: `prompts/templates/interview/tech_questions.yaml`
- [x] 文件: `prompts/templates/interview/behavior_questions.yaml`
- [x] 实现:
  - 从 JD 提取技术栈 → 生成技术题
  - 从简历提取项目经历 → 生成行为题（STAR）
  - 每题含参考答案 + 评分标准
  - 按难度分级
- [x] 验收: 生成 10 题（技术+行为），含答案

### Task 3.7: 完善 Tracker Agent
- [x] 文件: `agents/tracker_agent.py`
- [x] 实现:
  - 创建投递记录到 DB
  - 初始化看板状态
  - 设置跟进提醒（next_follow_up）
- [x] 验收: 投递记录正确写入 DB

### Task 3.8: 更新 Graph Nodes 使用真实 Agent
- [x] 文件: `graph/nodes.py`
- [x] 改进: 将占位 node 替换为真实 Agent 实例调用
- [x] 验收: 完整 Graph 可端到端执行

---

## Phase 4: Tool 注册表

### Task 4.1: Tool Registry 实现
- [x] 文件: `tools/registry.py`
- [x] 实现:
  - @register_tool 装饰器
  - 自动发现子目录中的 Tool
  - 按 Agent 分组获取
  - 转换为 LangChain Tool 格式
- [x] 验收: Agent 可通过 registry 获取绑定的 Tools

---

## Phase 5: Memory/RAG 系统

### Task 5.1: Embedding Service
- [x] 文件: `memory/embeddings.py`
- [x] 实现:
  - EmbeddingService 类
  - embed_text(text) → list[float]
  - embed_batch(texts) → list[list[float]]
  - 支持 OpenAI / 本地模型切换
- [x] 验收: 文本向量化正常

### Task 5.2: Vector Store
- [x] 文件: `memory/vectorstore.py`
- [x] 实现:
  - VectorStore 接口
  - PgVectorStore 实现（使用 pgvector）
  - add_documents / similarity_search
- [x] 验收: 向量存储和检索正常

### Task 5.3: Memory Store
- [x] 文件: `memory/store.py`
- [x] 实现:
  - MemoryStore 接口
  - PostgresMemoryStore 实现
  - save_memory / get_memory / search_memories
  - 跨会话用户偏好存储
- [x] 验收: 记忆 CRUD + 语义搜索

### Task 5.4: RAG Pipeline
- [x] 文件: `memory/rag.py`
- [x] 实现:
  - RAGPipeline 类
  - index_resume(resume) → 分段 + 向量化 + 存储
  - retrieve_relevant(query, top_k) → 相关片段
- [x] 验收: 简历分段检索正确

---

## Phase 6: Harness Runtime 完善

### Task 6.1: Trace Manager
- [x] 文件: `harness/trace_manager.py`
- [x] 实现:
  - LangGraph Callback 实现
  - 记录每个 Node: 开始/结束时间、输入/输出、Token
  - 写入 agent_logs 表
  - 可选集成 Langfuse
- [x] 验收: 执行后 agent_logs 表有记录

### Task 6.2: Guard Rails
- [x] 文件: `harness/guard_rails.py`
- [x] 实现:
  - TokenBudgetGuard: 超预算检查
  - StepLimitGuard: 步数上限
  - LoopDetectionGuard: 同 Node 重复执行检测
  - OutputValidationGuard: Pydantic 校验输出
  - 中间件链: before_node() / after_node()
- [x] 验收: 超步数/超 Token 时正确拦截

### Task 6.3: Budget Controller
- [x] 文件: `harness/budget_controller.py`
- [x] 实现:
  - 实时 Token 计数
  - 80% 告警
  - 100% 降级到小模型或终止
- [x] 验收: Token 超限时触发降级

### Task 6.4: Recovery Manager
- [x] 文件: `harness/recovery_manager.py`
- [x] 实现:
  - 指数退避重试 (1s, 2s, 4s)
  - Checkpoint 回滚
  - 模型降级 (deepseek-v4-pro → deepseek-v4-flash)
  - 平台不可用跳过
- [x] 验收: 连续失败 3 次后触发恢复

### Task 6.5: HITL Gateway
- [x] 文件: `harness/hitl_gateway.py`
- [x] 实现:
  - create_approval_request()
  - process_approval_response()
  - check_timeout()
  - 与 LangGraph interrupt 机制集成
  - WebSocket 通知
- [x] 验收: 审批请求创建 → 用户响应 → Graph 恢复

### Task 6.6: Eval Framework
- [x] 文件: `harness/eval/engine.py`
- [x] 文件: `harness/eval/metrics.py`
- [x] 文件: `harness/eval/judges.py`
- [x] 实现:
  - EvalEngine: 采样/批量/回归评估
  - 指标: 准确率、覆盖率、一致性
  - 评判器: Rule-based / LLM-as-Judge
- [x] 验收: 可运行评估并输出报告

---

## Phase 7: 集成与测试

### Task 7.1: Alembic 迁移初始化
- [x] 初始化 alembic（async 模式）
- [x] 生成初始迁移（10 张表）
- [x] 验收: `alembic upgrade head` 成功

### Task 7.2: 单元测试
- [x] `tests/unit/test_agents/test_intent_agent.py` — 3+ 用例
- [x] `tests/unit/test_tools/test_dedup.py`
- [x] `tests/unit/test_harness/test_guard_rails.py`
- [x] 验收: pytest 通过

### Task 7.3: 集成测试
- [x] `tests/integration/test_api/test_auth.py` — 注册/登录/刷新
- [x] `tests/integration/test_api/test_health.py`
- [x] `tests/integration/test_graph/test_main_flow.py` — 端到端
- [x] 验收: 完整流程跑通

### Task 7.4: conftest.py 完善
- [x] 异步 DB fixture（test DB）
- [x] Redis fixture
- [x] FastAPI TestClient (httpx AsyncClient)
- [x] 认证 fixture（自动注册 + Token）

### Task 7.5: Scripts
- [x] `scripts/init_db.py` — 创建 pgvector 扩展 + 初始化
- [x] `scripts/seed_data.py` — 测试用户 + 示例岗位

---

## 执行顺序建议

```
Phase 2 (API 补全)
  ├── Task 2.1 Jobs API
  ├── Task 2.2 Applications API
  ├── Task 2.3 Sessions API ← 核心
  ├── Task 2.4 Approvals API ← 核心
  ├── Task 2.5 Interview API
  ├── Task 2.6 Memory API
  └── Task 2.7 Monitoring API

Phase 3 (Agent 真实逻辑)
  ├── Task 3.1 Intent Agent 完善
  ├── Task 3.2 Search Agent + 爬虫
  ├── Task 3.3 Parse Agent + 解析
  ├── Task 3.4 Match Agent + 匹配
  ├── Task 3.5 Resume Agent + 优化
  ├── Task 3.6 Interview Agent + 出题
  ├── Task 3.7 Tracker Agent
  └── Task 3.8 Graph Nodes 更新 ← 串联

Phase 4 (Tool 注册表)
  └── Task 4.1 Registry

Phase 5 (Memory/RAG)
  ├── Task 5.1 Embedding
  ├── Task 5.2 VectorStore
  ├── Task 5.3 MemoryStore
  └── Task 5.4 RAG Pipeline

Phase 6 (Harness)
  ├── Task 6.1 Trace
  ├── Task 6.2 Guard Rails
  ├── Task 6.3 Budget
  ├── Task 6.4 Recovery
  ├── Task 6.5 HITL Gateway
  └── Task 6.6 Eval

Phase 7 (测试)
  ├── Task 7.1 Alembic
  ├── Task 7.2 单元测试
  ├── Task 7.3 集成测试
  ├── Task 7.4 conftest
  └── Task 7.5 Scripts
```

---

## 使用方式

每次开始实现前：
1. 打开本文档
2. 找到当前要实现的 Task
3. 确认依赖的 Task 已完成
4. 实现功能
5. 运行验收标准
6. 在本文档中标记 `[x]` 完成
