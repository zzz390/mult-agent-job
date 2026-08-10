# Job Agent OS 代码审查报告

> **生成日期**：2026-07-29  
> **审查范围**：后端 Agent/Graph/Harness 层、后端 API/服务/模型层、前端代码及前后端集成  
> **项目路径**：`job-agent-os/`

---

## 目录

- [一、问题严重度分级](#一问题严重度分级)
- [二、后端 Agent 层问题](#二后端-agent-层问题)
- [三、后端 Graph 层问题](#三后端-graph-层问题)
- [四、后端 Harness 层问题](#四后端-harness-层问题)
- [五、后端 API 层问题](#五后端-api-层问题)
- [六、后端服务层问题](#六后端服务层问题)
- [七、后端数据模型问题](#七后端数据模型问题)
- [八、后端 Schema 与模型匹配问题](#八后端-schema-与模型匹配问题)
- [九、后端数据库会话管理问题](#九后端数据库会话管理问题)
- [十、后端安全问题](#十后端安全问题)
- [十一、后端配置与 Memory/RAG 问题](#十一后端配置与-memoryrag-问题)
- [十二、前端代码问题](#十二前端代码问题)
- [十三、前后端集成问题](#十三前后端集成问题)
- [十四、死代码与空实现汇总](#十四死代码与空实现汇总)
- [十五、修复优先级建议](#十五修复优先级建议)

---

## 一、问题严重度分级

| 级别 | 说明 | 数量 |
|------|------|------|
| **P0 — 严重** | 导致功能完全不工作或存在安全漏洞，必须立即修复 | 8 |
| **P1 — 高** | 影响核心功能或存在较大风险，应尽快修复 | 12 |
| **P2 — 中** | 影响可维护性或用户体验，计划修复 | 18 |
| **P3 — 低** | 代码质量或轻微问题，择机修复 | 14 |

---

## 二、后端 Agent 层问题

### 2.1 【P0】tracker_node 函数体为空，投递管理功能完全不工作

- **文件**：`src/job_agent_os/graph/nodes.py`，第 67-69 行
- **描述**：`tracker_node` 函数只有 docstring，没有 `return await tracker_agent.execute(state)` 语句。函数返回 `None`，LangGraph 会尝试将 `None` 合并到 state，导致投递创建步骤被静默跳过。
- **修复建议**：补充 `return await tracker_agent.execute(state)`。

### 2.2 【P0】resume_agent 空结果导致 Supervisor 无限循环

- **文件**：`src/job_agent_os/agents/resume_agent.py`，第 97 行
- **描述**：`return {"optimized_resume": optimized_resume or {}}` — 当优化失败时返回空 dict `{}`。空 dict 是 falsy，Supervisor 的 `_fallback_decision`（supervisor.py 第 225 行）检查 `if not state.get("optimized_resume")`，空 dict 为 falsy，会再次路由到 resume agent，可能导致无限循环。
- **修复建议**：使用 `None` 替代空 dict，或在 Supervisor 中添加循环检测。

### 2.3 【P0】web_search_agent 覆盖 search_results 导致数据丢失

- **文件**：`src/job_agent_os/agents/web_search_agent.py`，第 87 行
- **描述**：返回 `"search_results": all_jobs`，由于 state.py 中 `search_results` 没有 reducer，LangGraph 会用此值**替换**之前 search agent 的数据库查询结果，导致已搜索到的岗位数据丢失。同时第 89 行 `platforms_searched` 也被覆盖为 `["web_career_sites"]`。
- **修复建议**：为 `search_results` 和 `platforms_searched` 添加 reducer（如 `operator.add`），或在 web_search_agent 中合并旧数据。

### 2.4 【P1】ToolMessage 缺少 name 属性导致 _extract_tool_results 失效

- **文件**：`src/job_agent_os/agents/base.py`，第 141-143 行（创建）、第 174 行（检查）
- **描述**：ToolMessage 创建时只传了 `content` 和 `tool_call_id`，未传 `name`。但 `_extract_tool_results` 方法依赖 `msg.name == tool_name` 来过滤结果，此方法永远返回空列表。
- **修复建议**：创建 ToolMessage 时补充 `name=tool_name` 参数。

### 2.5 【P1】Fallback LLM 在 execute() 中从未使用

- **文件**：`src/job_agent_os/agents/base.py`，第 43、47-58、87 行
- **描述**：`_llm_fallback` 实例变量在构造函数中初始化，`_get_llm(use_fallback=True)` 方法存在，但 `_build_react_executor()` 调用 `self._get_llm()` 不带参数，始终使用主 LLM。BudgetController 和 RecoveryManager 设计的模型降级机制无法实际生效。
- **修复建议**：在异常处理或预算超限时切换到 fallback LLM。

### 2.6 【P1】ReAct 循环异常处理不充分

- **文件**：`src/job_agent_os/agents/base.py`，第 110-115 行
- **描述**：LLM 调用失败时仅 `break` 跳出循环，然后直接调用 `_parse_final_output`。没有设置错误状态、没有重试、没有通知上层。如果第一次迭代就失败，`messages` 列表中只有初始消息，`_parse_final_output` 可能返回空结果或默认值。
- **修复建议**：添加重试机制或在失败时设置明确的错误状态。

### 2.7 【P1】Supervisor JSON 解析脆弱性

- **文件**：`src/job_agent_os/agents/supervisor.py`，第 130-149 行
- **描述**：`_parse_decision_json` 使用字符串分割提取 JSON。如果 LLM 返回嵌套代码块（如 ```` ```json ```json ``` ````）或 JSON 内部包含 ```` ``` ```` 字符串，解析会截断。虽然有外层 try/except 兜底，但会导致非预期的 fallback 路由。
- **修复建议**：使用正则表达式或更健壮的 JSON 提取方法。

### 2.8 【P2】match_agent 模糊技能匹配导致误匹配

- **文件**：`src/job_agent_os/agents/match_agent.py`，第 83 行
- **描述**：`s.lower() in us.lower() or us.lower() in s.lower()` — 子串匹配。例如 "Java" 会匹配 "JavaScript"（因为 "java" in "javascript"），导致虚假的高匹配分数。
- **修复建议**：使用精确匹配或更智能的相似度算法（如 difflib）。

### 2.9 【P2】parse_agent fallback 使用假置信度绕过阈值

- **文件**：`src/job_agent_os/agents/parse_agent.py`，第 87-103 行
- **描述**：当所有解析都失败时，直接将原始搜索结果作为 parsed_jobs 返回，设置 `parse_confidence: 0.5`。这绕过了 0.6 的阈值要求，可能误导下游 match agent。
- **修复建议**：fallback 时设置低置信度并添加标记，或让下游感知数据未解析。

### 2.10 【P2】search_agent platforms_searched 追踪不完整

- **文件**：`src/job_agent_os/agents/search_agent.py`，第 79-82 行
- **描述**：只有 `query_jobs_db` 返回的结果会添加 "database" 到 `platforms_searched`。boss_search、guopin_search、niuke_search 的结果被合并但不记录对应平台名称。
- **修复建议**：为每个工具调用结果记录平台名称。

### 2.11 【P2】resume_agent 和 interview_agent 直接索引可能 KeyError

- **文件**：`src/job_agent_os/agents/resume_agent.py` 第 41 行、`src/job_agent_os/agents/interview_agent.py` 第 40 行
- **描述**：`match_results[0]["job"]` — 如果 match_results 非空但第一个元素没有 "job" 键，会抛出 KeyError。虽然 match agent 总是包含 "job"，但这依赖上游实现不变。
- **修复建议**：使用 `.get("job", {})` 或添加键存在性检查。

### 2.12 【P2】tracker_agent system_prompt 提到 save_jobs_db 但未注册为工具

- **文件**：`src/job_agent_os/agents/tracker_agent.py`，第 30 行
- **描述**：`agent_tools = ["query_jobs_db"]`，但 system prompt（第 14 行）提到可以使用 `save_jobs_db`。LLM 可能尝试调用不存在的工具。
- **修复建议**：将 `save_jobs_db` 添加到 `agent_tools` 列表，或修改 system prompt。

### 2.13 【P2】tracker_agent _parse_final_output 完全忽略工具调用结果

- **文件**：`src/job_agent_os/agents/tracker_agent.py`，第 53-85 行
- **描述**：直接从 `state.get("match_results")` 构建 applications，不读取任何 ToolMessage。ReAct 循环中 LLM 调用 `query_jobs_db` 的结果被完全忽略。
- **修复建议**：读取工具调用结果来构建 applications 数据。

### 2.14 【P2】Supervisor 继承 BaseAgent 但不使用 execute()

- **文件**：`src/job_agent_os/agents/supervisor.py`，第 256-262 行
- **描述**：`_build_initial_messages` 和 `_parse_final_output` 返回空值。如果有人误调用 `supervisor_agent.execute(state)`，将返回空 dict，导致图卡死。
- **修复建议**：覆盖 `execute()` 方法抛出明确的异常，或重命名为 `route()`。

### 2.15 【P3】Supervisor 仅捕获第一条用户消息

- **文件**：`src/job_agent_os/agents/supervisor.py`，第 168-170 行
- **描述**：`user_intent` 变量在 for 循环中被覆盖但循环结束后保留第一个 HumanMessage 的内容。后续澄清消息被忽略。
- **修复建议**：收集所有 HumanMessage 或合并为单一上下文。

### 2.16 【P3】intent_agent fallback 关键词硬编码且不完整

- **文件**：`src/job_agent_os/agents/intent_agent.py`，第 123-125 行
- **描述**：地区列表只包含 12 个城市，企业类型和岗位方向也是硬编码的。未在列表中的地区/方向，fallback 解析会失败。
- **修复建议**：使用配置文件或数据库管理关键词列表。

---

## 三、后端 Graph 层问题

### 3.1 【P0】列表字段缺少 reducer 导致数据覆盖

- **文件**：`src/job_agent_os/graph/state.py`，第 47-69 行
- **描述**：只有 `messages` 字段使用了 `add_messages` reducer。`search_results`、`parsed_jobs`、`match_results`、`applications`、`execution_log` 等列表字段都没有 reducer。当 Agent 返回这些字段时，LangGraph 默认用新值**覆盖**旧值。
- **修复建议**：为所有列表字段添加 `operator.add` 或自定义合并 reducer。

### 3.2 【P1】生产环境 checkpointer 未实现

- **文件**：`src/job_agent_os/graph/checkpointer.py`，第 16-20 行
- **描述**：当 `settings.env == "prod"` 时，代码块只有 `pass`，然后直接返回 `MemorySaver()`。生产环境也会使用内存检查点，重启即丢失状态。PostgresSaver 的导入被注释掉。
- **修复建议**：实现并启用 AsyncPostgresSaver。

### 3.3 【P1】未配置 interrupt_before 节点，HITL 机制不可用

- **文件**：`src/job_agent_os/graph/main_graph.py`，第 89 行
- **描述**：`workflow.compile(checkpointer=checkpointer)` 没有配置 `interrupt_before` 参数。HITLGateway 设计了完整的人机交互流程，但图编译时没有设置任何中断点。
- **修复建议**：在 resume_agent 或其他需要审批的节点前配置 `interrupt_before`。

### 3.4 【P1】全局单例图实例 + 共享 MemorySaver

- **文件**：`src/job_agent_os/graph/main_graph.py`，第 92-101 行
- **描述**：`_main_graph` 是全局单例，所有会话共享同一编译图和同一 MemorySaver checkpointer。生产环境下多 worker 之间无法共享检查点。
- **修复建议**：在生产环境使用基于 PostgreSQL 的 checkpointer。

### 3.5 【P3】edges.py 末尾有死代码

- **文件**：`src/job_agent_os/graph/edges.py`，第 27-29 行
- **描述**：`return "__end__"` 之后有字符串字面量 `"""Conditional edges and routing functions."""`，是不可达代码。
- **修复建议**：删除或移至文件开头作为模块 docstring。

---

## 四、后端 Harness 层问题

### 4.1 【P0】所有 Harness 保护机制均未集成

- **文件**：`src/job_agent_os/harness/runtime.py`，第 53-55 行
- **描述**：`execute()` 方法直接调用 `graph.ainvoke(initial_state, config)`，没有调用 GuardRailChain、BudgetController、RecoveryManager 或 TraceManager。类文档声称提供"guard rails、error recovery、tracing"，但实际执行路径中这些组件全部缺席。
- **修复建议**：在 `execute()` 中集成 Harness 组件，包裹 graph 调用。

### 4.2 【P1】cancel_session 不会实际取消执行

- **文件**：`src/job_agent_os/harness/runtime.py`，第 71-76 行
- **描述**：只修改 `_active_sessions` 中的状态标记为 "cancelled"，但正在运行的 `graph.ainvoke()` 调用不会被打断。
- **修复建议**：通过 `asyncio.Task.cancel()` 实现实际取消。

### 4.3 【P1】_active_sessions 内存泄漏

- **文件**：`src/job_agent_os/harness/runtime.py`，第 22、47 行
- **描述**：会话完成后只更新 status 字段，不从 dict 中移除。长时间运行的服务会累积大量已完成的会话记录。
- **修复建议**：添加定期清理机制或在会话完成后移除记录。

### 4.4 【P1】会话跟踪数据不更新

- **文件**：`src/job_agent_os/harness/runtime.py`，第 47-51、58 行
- **描述**：初始化时设置 `steps: 0` 和 `tokens_used: 0`，但执行过程中从不更新这些字段。
- **修复建议**：在 graph 执行过程中通过 callback 更新步骤和 token 使用量。

### 4.5 【P1】RecoveryManager _use_fallback 注入会导致 TypeError

- **文件**：`src/job_agent_os/harness/recovery_manager.py`，第 165 行
- **描述**：`kwargs["_use_fallback"] = True` 会将 `_use_fallback` 作为关键字参数传给被包装的异步函数。但 Agent 的 `execute()` 方法签名是 `async def execute(self, state)` 不接受此参数，会抛出 TypeError。
- **修复建议**：修改 execute 方法签名接受 `_use_fallback` 参数，或使用其他机制传递降级信号。

### 4.6 【P1】TraceManager error_type 计算逻辑错误

- **文件**：`src/job_agent_os/harness/trace_manager.py`，第 112 行
- **描述**：`type(error_message).__name__` — `error_message` 是字符串（来自 `str(error)`）。`type("some string").__name__` 永远返回 `"str"`。应该存储实际的异常类型。
- **修复建议**：存储异常对象本身或其类型名。

### 4.7 【P2】flush_to_db 无条件清空日志导致数据丢失

- **文件**：`src/job_agent_os/harness/trace_manager.py`，第 182 行
- **描述**：即使部分日志因缺少 session_id/user_id 而跳过写入（第 151-152 行），`self._logs = []` 仍会清空所有日志，导致跳过的日志永久丢失。
- **修复建议**：只清空已成功写入的日志，保留跳过的日志。

### 4.8 【P2】GuardRailChain OutputValidationGuard 不检查 required_fields

- **文件**：`src/job_agent_os/harness/guard_rails.py`，第 130-137 行
- **描述**：`__init__` 接收 `required_fields`（默认 `["current_phase"]`），但 `after_node` 方法完全不检查这些字段是否存在。
- **修复建议**：在 `after_node` 中实现字段存在性检查。

### 4.9 【P2】BudgetController._history 无上限

- **文件**：`src/job_agent_os/harness/budget_controller.py`，第 54、59 行
- **描述**：每次 `record_usage` 都 append 到 `_history`，无大小限制。长时间运行会消耗内存。
- **修复建议**：使用 `collections.deque(maxlen=...)` 或添加清理逻辑。

### 4.10 【P2】RecoveryManager last_error 可能为 None

- **文件**：`src/job_agent_os/harness/recovery_manager.py`，第 151、172 行
- **描述**：`last_error: Exception | None = None`，如果循环正常结束，`raise last_error` 会变成 `raise None`，抛出 TypeError 而非预期的异常。
- **修复建议**：在 raise 前检查 `last_error is not None`。

---

## 五、后端 API 层问题

### 5.1 【P1】resumes.py 依赖注入方式错误

- **文件**：`src/job_agent_os/api/v1/resumes.py`，第 18-19、45-47、74-75、96-97、137-138 行
- **描述**：所有路由函数中 `CurrentUser` 和 `DBSession` 依赖使用了 `= None` 默认值，而非标准的 FastAPI 依赖注入方式。虽然 `Annotated[T, Depends(...)]` 在 FastAPI 中仍会触发依赖注入，但 `= None` 默认值使类型标注暗示参数可为 None，且与项目其他文件不一致。
- **修复建议**：移除 `= None` 默认值，统一使用 `db: DBSession, user: CurrentUser` 方式。

### 5.2 【P2】resumes.py 中无用的查询语句

- **文件**：`src/job_agent_os/api/v1/resumes.py`，第 115-117 行
- **描述**：SELECT 查询结果完全未被使用，紧接着才执行了实际的 UPDATE 操作。这是一段死代码，浪费数据库资源。
- **修复建议**：删除无用的 SELECT 查询。

### 5.3 【P2】evaluations.py 和 monitoring.py 绕过服务层直接操作数据库

- **文件**：`src/job_agent_os/api/v1/evaluations.py` 第 19-37 行、`src/job_agent_os/api/v1/monitoring.py` 第 53-86 行
- **描述**：路由处理器直接在函数内部编写 SQLAlchemy 查询逻辑，违反了分层架构原则。
- **修复建议**：将业务逻辑移至服务层。

### 5.4 【P2】evaluations.py 和 monitoring.py 的 days 参数未生效

- **文件**：`src/job_agent_os/api/v1/evaluations.py` 第 15 行、`src/job_agent_os/api/v1/monitoring.py` 第 50 行
- **描述**：`days` 参数被接收但从未用于过滤查询。SQL 查询没有添加任何日期范围条件。
- **修复建议**：在查询中添加 `created_at >= datetime.now() - timedelta(days=days)` 条件。

### 5.5 【P2】interview.py 内存任务存储无清理机制

- **文件**：`src/job_agent_os/api/v1/interview.py`，第 18 行
- **描述**：`_generation_tasks: dict[str, dict] = {}` 是进程内字典，无过期清理、无大小限制。长期运行将导致内存泄漏。
- **修复建议**：添加 TTL 清理机制或使用 Redis 存储。

### 5.6 【P3】prompts.py 空路由

- **文件**：`src/job_agent_os/api/v1/prompts.py`
- **描述**：注册了空路由器但无任何端点，在 router.py 中被注册。
- **修复建议**：移除或在 router.py 中注释掉注册。

---

## 六、后端服务层问题

### 6.1 【P0】session_service.py 中不存在的方法被调用

- **文件**：`src/job_agent_os/services/approval_service.py`，第 121 行
- **描述**：`service.resume_session(session_id)` — `SessionService` 类中并未定义 `resume_session` 方法。此调用会在运行时抛出 `AttributeError`，但被第 122-124 行的 `except Exception: pass` 静默吞掉。
- **修复建议**：在 `SessionService` 中实现 `resume_session` 方法，或修改调用方式。

### 6.2 【P0】后台任务使用已关闭的数据库会话

- **文件**：`src/job_agent_os/services/approval_service.py`，第 120-121 行
- **描述**：`service = SessionService(self.db)` 使用当前请求的数据库会话。当 HTTP 请求结束后，`get_db_session()` 会 commit 并 close 会话。但后台任务可能在请求结束后才执行，此时 `self.db` 已关闭。
- **修复建议**：使用 `get_session_factory()` 创建独立会话。

### 6.3 【P1】后台任务引用未保持

- **文件**：`src/job_agent_os/services/session_service.py` 第 100 行、`src/job_agent_os/services/approval_service.py` 第 121 行
- **描述**：使用 `asyncio.create_task(...)` 但均未保持任务引用。Python 的垃圾回收器可能在任意时刻回收未被引用的 Task 对象，导致任务被静默取消。
- **修复建议**：将任务引用存储在集合中，并添加 `add_done_callback` 清理。

### 6.4 【P1】session_service.py 状态检查不一致

- **文件**：`src/job_agent_os/services/session_service.py`，第 287 行
- **描述**：检查 `info["status"] == "error"`，但失败状态在第 145 行被设置为 `"failed"` 而非 `"error"`。会话失败时，timeline 端点永远不会返回 `session_error` 事件。
- **修复建议**：统一状态字符串，将 `"error"` 改为 `"failed"`。

### 6.5 【P2】approval_service.py 静默吞掉所有异常

- **文件**：`src/job_agent_os/services/approval_service.py`，第 122-124 行
- **描述**：`except Exception: pass` — 图恢复失败的异常被完全静默，无法调试。用户也不会收到任何错误提示，会话将永远停留在等待状态。
- **修复建议**：添加日志记录并设置会话错误状态。

### 6.6 【P2】session_service.py 异常处理使用 print 而非 logging

- **文件**：`src/job_agent_os/services/session_service.py`，第 142-143 行
- **描述**：使用 `traceback.print_exc()` 而非 `logger.exception()`，不符合日志最佳实践。
- **修复建议**：替换为 `logger.exception()`。

### 6.7 【P2】auth_service.py register 后重复查询

- **文件**：`src/job_agent_os/services/auth_service.py` + `src/job_agent_os/api/v1/auth.py` 第 28 行
- **描述**：`register()` 方法已创建并返回 User 对象，但 `auth.py` 的 register 端点又调用 `service.login()`，重新查询数据库并再次验证密码。
- **修复建议**：在 `register` 方法中直接生成 token。

### 6.8 【P2】动态排序字段安全风险

- **文件**：`src/job_agent_os/services/application_service.py` 第 102 行、`src/job_agent_os/services/job_service.py` 第 60 行
- **描述**：`getattr(Application, pagination.sort_by, Application.created_at)` — `pagination.sort_by` 来自用户输入，未限制可选值。可能暴露不期望排序的字段。
- **修复建议**：在 schema 中用 `Literal` 或 `pattern` 约束可选排序字段。

### 6.9 【P3】job_service.py 错误码语义不匹配

- **文件**：`src/job_agent_os/services/job_service.py`，第 99 行
- **描述**：使用 `DUPLICATE_APPLICATION` 错误码来表示重复的岗位条目，语义不正确。
- **修复建议**：添加岗位模块的重复错误码。

---

## 七、后端数据模型问题

### 7.1 【P2】Application.resume_id 缺少用户归属校验

- **文件**：`src/job_agent_os/models/application.py`，第 27 行
- **描述**：`resume_id` 仅有外键约束，但无数据库级约束确保该简历属于同一用户。服务层也未验证 `resume_id` 是否属于当前用户。攻击者可通过传入其他用户的 `resume_id` 创建关联。
- **修复建议**：在 `ApplicationService.create_application` 中验证 `resume_id` 归属。

### 7.2 【P2】多个模型的 session_id 缺少外键约束

- **文件**：`models/human_approval.py` 第 20 行、`models/agent_log.py` 第 19 行、`models/tool_call.py` 第 19 行、`models/evaluation.py` 第 19 行
- **描述**：这些字段声明为 `session_id: Mapped[UUID]` 但无 `ForeignKey` 约束，无法在数据库层面保证引用完整性。
- **修复建议**：如果会话存储在数据库中，添加 ForeignKey 约束；否则考虑添加应用层校验。

### 7.3 【P2】User 模型 lazy="selectin" 导致 N+1 查询问题

- **文件**：`src/job_agent_os/models/user.py`，第 37-38 行
- **描述**：`lazy="selectin"` 意味着每次加载 User 对象时都会自动加载其所有 resumes 和 applications。在认证流程中（`get_current_user`），每次请求都会触发两个额外的查询。
- **修复建议**：改为 `lazy="noload"` 或 `lazy="raise"`，在需要时显式 `selectinload`。

### 7.4 【P3】Application 和 Resume 关系定义不对称

- **文件**：`src/job_agent_os/models/application.py`，第 44-45 行
- **描述**：relationship 没有定义 `back_populates`，`Resume` 模型中也没有对应的反向关系。
- **修复建议**：添加 `back_populates` 双向关系。

---

## 八、后端 Schema 与模型匹配问题

### 8.1 【P2】ApprovalResponse 缺少响应后状态字段

- **文件**：`src/job_agent_os/schemas/approval.py`，第 9-22 行
- **描述**：`ApprovalResponse` 不包含 `action`、`feedback`、`modified_payload`、`responded_at` 字段。用户无法看到自己刚刚提交的审批动作和反馈。
- **修复建议**：补充这些字段到响应 schema。

### 8.2 【P2】ResumeResponse 缺少多个模型字段

- **文件**：`src/job_agent_os/schemas/resume.py`，第 53-66 行
- **描述**：未暴露 `raw_content`、`file_path`、`file_size_bytes`、`chunks`、`is_encrypted` 字段。
- **修复建议**：根据前端需求补充字段。

### 8.3 【P2】JobResponse 缺少部分字段

- **文件**：`src/job_agent_os/schemas/job.py`，第 52-70 行
- **描述**：未包含 `industry`、`salary_min`、`salary_max`、`experience_required`、`skills_preferred`、`headcount`、`job_type` 等字段，导致前端无法获取完整的岗位信息。
- **修复建议**：补充缺失字段。

---

## 九、后端数据库会话管理问题

### 9.1 【P0】db_tools.py 绕过请求会话独立提交

- **文件**：`src/job_agent_os/tools/common/db_tools.py`，第 50-51、96-99、134 行
- **描述**：`query_jobs_db` 和 `save_jobs_db` 工具函数各自创建独立的数据库会话并独立提交。当这些工具在请求处理流程中被调用时，存在两个独立会话，可能导致数据不一致、死锁风险和事务边界混乱。
- **修复建议**：使用请求上下文的会话，或确保工具会话与请求会话的隔离级别一致。

### 9.2 【P2】db/session.py 会话在 yield 后自动提交

- **文件**：`src/job_agent_os/db/session.py`，第 50-57 行
- **描述**：`yield session` 后自动 `await session.commit()`。如果业务逻辑有部分失败但未抛出异常，仍会被提交。
- **修复建议**：考虑使用更严格的事务管理策略，如显式 commit。

---

## 十、后端安全问题

### 10.1 【P0】CORS 配置允许所有来源携带凭证

- **文件**：`src/job_agent_os/api/middleware.py`，第 68-74 行
- **描述**：`allow_origins=["*"]` 配合 `allow_credentials=True` 是一个安全问题。生产环境中应将 `allow_origins` 限制为具体的前端域名列表。
- **修复建议**：将 `allow_origins` 设置为具体的前端域名列表，从环境变量读取。

### 10.2 【P0】JWT 默认密钥为硬编码值

- **文件**：`src/job_agent_os/settings.py`，第 103 行
- **描述**：`jwt_secret_key: SecretStr = SecretStr("your-super-secret-key-change-in-production")`。如果 `.env` 文件未覆盖此值，JWT 令牌使用已知的弱密钥签名，任何人都可以伪造有效的 JWT 令牌。
- **修复建议**：在应用启动时检查是否为默认值，如果是则拒绝启动。

### 10.3 【P1】未验证 token 类型

- **文件**：`src/job_agent_os/api/deps.py`，第 34 行
- **描述**：`get_current_user` 函数解码 JWT 后未检查 `payload.get("type") == "access"`。refresh token 也可用于 API 认证，绕过了 token 类型隔离。
- **修复建议**：添加 token 类型校验。

### 10.4 【P1】Bearer token 解析方式不安全

- **文件**：`src/job_agent_os/api/deps.py`，第 33 行
- **描述**：`authorization.replace("Bearer ", "")` 会替换所有出现的 "Bearer " 子串。应使用 `authorization.removeprefix("Bearer ")`。
- **修复建议**：使用 `removeprefix` 替代 `replace`。

### 10.5 【P2】密码静默截断

- **文件**：`src/job_agent_os/core/security.py`，第 15、21 行
- **描述**：`password.encode("utf-8")[:72]` 静默截断会导致不同密码（前 72 字节相同）被视为相同。
- **修复建议**：在截断前警告用户或拒绝超长密码。

### 10.6 【P3】注册无邮箱验证

- **文件**：`src/job_agent_os/services/auth_service.py`，第 29-63 行
- **描述**：直接创建状态为 `"active"` 的用户，无邮箱验证步骤。
- **修复建议**：添加邮箱验证流程（可选，取决于安全要求）。

---

## 十一、后端配置与 Memory/RAG 问题

### 11.1 【P2】settings.py 中 lru_cache 阻止运行时配置刷新

- **文件**：`src/job_agent_os/settings.py`，第 209-212 行
- **描述**：`@lru_cache` 使配置在首次加载后被缓存，运行时修改环境变量不会更新。
- **修复建议**：在测试场景中提供 `get_settings.cache_clear()` 调用方式。

### 11.2 【P2】embedding_model 名称可能不正确

- **文件**：`src/job_agent_os/settings.py`，第 120 行
- **描述**：`embedding_model: str = "qwen3.7-text-embedding"` — DashScope 的 embedding 模型名称通常为 `text-embedding-v3` 或 `text-embedding-v2`，可能导致 API 调用失败。
- **修复建议**：验证并更正模型名称。

### 11.3 【P2】MemoryStore.get_memory 副作用未持久化

- **文件**：`src/job_agent_os/memory/store.py`，第 148-150 行
- **描述**：修改了 ORM 对象的 `access_count` 和 `last_accessed_at`，但未调用 `flush`，修改可能不会被持久化。
- **修复建议**：在修改后调用 `await db.flush()`。

### 11.4 【P2】embeddings.py 全局单例未关闭客户端

- **文件**：`src/job_agent_os/memory/embeddings.py`，第 104-112 行
- **描述**：全局 `_embedding_service` 单例持有一个 `httpx.AsyncClient`，但应用关闭时没有对应的清理函数。
- **修复建议**：在 `main.py` 的 lifespan shutdown 阶段调用 `get_embedding_service().close()`。

### 11.5 【P3】rag.py 文本分块不感知语言边界

- **文件**：`src/job_agent_os/memory/rag.py`，第 152-164 行
- **描述**：按字符数分块，不感知单词或句子边界，可能在词语中间截断。
- **修复建议**：使用基于句号/换行符的分块策略。

### 11.6 【P3】vectorstore.py 使用 raw SQL text 排序

- **文件**：`src/job_agent_os/memory/vectorstore.py`，第 117 行
- **描述**：`order_by(text("similarity DESC"))` 是脆弱的写法。
- **修复建议**：使用 SQLAlchemy 列表达式。

### 11.7 【P3】多个配置子类未被使用

- **文件**：`src/job_agent_os/settings.py`，第 10-73 行
- **描述**：定义了多个子配置类，但仅通过 `@property` 方法返回，实际使用的都是扁平字段。
- **修复建议**：移除未使用的子类或重构为嵌套配置。

---

## 十二、前端代码问题

### 12.1 【P1】多个页面组件错误处理静默吞错

- **文件**：
  - `frontend/src/app/(main)/jobs/page.tsx` 第 49 行：`catch { setJobs([]); setPagination(null); }`
  - `frontend/src/app/(main)/kanban/page.tsx` 第 63 行：`catch { setKanban(null); }`
  - `frontend/src/app/(main)/resume/page.tsx` 第 26 行：`catch { setResumes([]); }`
- **描述**：API 失败时用户只看到空列表，不知道是网络错误还是权限问题。
- **修复建议**：使用 `toast.error()` 显示错误信息，参考 `settings/page.tsx` 的做法。

### 12.2 【P1】API 客户端缺少超时处理

- **文件**：`frontend/src/lib/api/client.ts`，第 85 行
- **描述**：`fetch()` 调用没有设置超时（如 AbortController）。网络异常时请求会无限挂起，用户界面会一直处于 loading 状态。
- **修复建议**：使用 `AbortController` 添加超时处理。

### 12.3 【P2】useSession hook 轮询无并发保护

- **文件**：`frontend/src/lib/hooks/useSession.ts`，第 113-175 行
- **描述**：`poll()` 是 async 函数，通过 `setInterval(poll, POLL_INTERVAL)` 调用。如果单次 `poll()` 耗时超过 2000ms，多个 `poll()` 会并发执行，可能导致重复的 API 调用和重复添加聊天消息。
- **修复建议**：添加 `isPolling` 标志防止并发 poll，或使用递归 `setTimeout` 替代 `setInterval`。

### 12.4 【P2】useSession hook 的 isPolling 值不会响应式更新

- **文件**：`frontend/src/lib/hooks/useSession.ts`，第 210 行
- **描述**：`isPolling: timer !== null` 中的 `timer` 是模块级变量，其变化不会触发 React 重渲染。
- **修复建议**：将 timer 状态移入 store 或使用 `useState` 管理。

### 12.5 【P2】ChatPage handleSend 状态管理脆弱

- **文件**：`frontend/src/app/(main)/chat/page.tsx`，第 28-39 行
- **描述**：当创建新会话时，先 `clear()` 然后手动重新设置状态，依赖于 `clear()` 的具体实现细节。
- **修复建议**：重构状态管理逻辑，减少对实现细节的依赖。

### 12.6 【P2】ContextPanel 中 TOKEN_BUDGET 硬编码

- **文件**：`frontend/src/components/chat/ContextPanel.tsx`，第 10 行
- **描述**：`const TOKEN_BUDGET = 100000;` 硬编码，而用户实际预算来自 `user.token_budget_daily`。
- **修复建议**：从用户数据动态读取预算值。

### 12.7 【P2】ResumeCard 的 catch 块完全静默

- **文件**：`frontend/src/components/resume/ResumeCard.tsx`，第 27 行
- **描述**：`catch { // ignore }` — 设置活跃简历失败时用户无任何反馈。
- **修复建议**：添加 `toast.error()` 错误提示。

### 12.8 【P3】isBusy 逻辑中 null 值检查冗余

- **文件**：`frontend/src/app/(main)/chat/page.tsx`，第 72-77 行
- **描述**：`null` 在数组中是多余的，因为 `sessionStatus !== null` 已在外层检查。
- **修复建议**：移除数组中的 `null`。

### 12.9 【P3】useSession.ts 使用 NodeJS.Timeout 类型

- **文件**：`frontend/src/lib/hooks/useSession.ts`，第 22 行
- **描述**：在浏览器环境中，`setInterval` 返回 `number` 类型。使用 `NodeJS.Timeout` 语义不正确。
- **修复建议**：使用 `ReturnType<typeof setInterval>` 或 `number`。

### 12.10 【P3】ResumeUploader eslint 抑制

- **文件**：`frontend/src/components/resume/ResumeUploader.tsx`，第 42-47 行
- **描述**：`onDrop` 依赖数组不完整，通过 eslint-disable 绕过检查。
- **修复建议**：完善依赖数组或使用 `useCallback` 的正确模式。

---

## 十三、前后端集成问题

### 13.1 【P1】Resume 上传绕过统一 API 客户端，缺少 401 刷新处理

- **文件**：`frontend/src/lib/api/resumes.ts`，第 8-40 行
- **描述**：`uploadResume` 函数直接使用 `fetch("/v1/resumes", ...)` 而非通过 `api.post()` 调用。不包含 401 token 刷新逻辑。文件上传耗时较长，token 过期概率较高。错误处理使用普通 `Error` 而非 `ApiError`，丢失了 `code` 和 `status` 信息。
- **修复建议**：重构为使用统一 API 客户端，或手动添加 401 刷新逻辑和 `ApiError` 处理。

### 13.2 【P1】InterviewQuestion 类型存在两套不兼容的定义

- **文件**：
  - `frontend/src/types/session.ts` 第 92-100 行（聊天卡片展示用）
  - `frontend/src/lib/api/interview.ts` 第 5-14 行（面试 API 用）
  - 后端 `src/job_agent_os/schemas/interview.py` 第 18-29 行
- **描述**：
  1. `types/session.ts` 的 `answer` 对应后端的 `reference_answer` — 字段名不一致
  2. `types/session.ts` 的 `scoring_criteria` 是 `string` 类型，而后端是 `list[str]` — 类型不匹配
  3. `types/session.ts` 缺少 `id` 和 `category` 字段
- **修复建议**：统一类型定义，消除两套不兼容的结构。

### 13.3 【P2】KanbanView.statistics 字段结构前后端未严格定义

- **文件**：后端 `src/job_agent_os/schemas/application.py` 第 57 行、前端 `frontend/src/types/application.ts` 第 37 行、`frontend/src/app/(main)/kanban/page.tsx` 第 95-97 行
- **描述**：后端 `statistics: dict` 无具体键约束，前端依赖未文档化的键名（`total`、`in_progress`、`offer_count`），可能导致运行时取到 `undefined`。
- **修复建议**：后端 schema 定义具体字段结构，前端类型同步更新。

### 13.4 【P2】API_BASE 配置依赖开发环境硬编码

- **文件**：`frontend/src/lib/api/client.ts` 第 5 行、`frontend/next.config.mjs` 第 7 行
- **描述**：`next.config.mjs` 中 `destination: "http://localhost:8000/v1/:path*"` 硬编码 localhost。生产部署时需要修改配置文件。
- **修复建议**：使用 `process.env.BACKEND_URL` 替代硬编码。

### 13.5 【P2】Token 存储在 localStorage 中存在 XSS 风险

- **文件**：`frontend/src/lib/api/client.ts`，第 16-19 行
- **描述**：access_token 和 refresh_token 都存储在 localStorage，任何 XSS 攻击都可以读取。
- **修复建议**：对于高安全要求的系统，考虑 httpOnly cookie 方案。

### 13.6 【P2】SessionMessageResponse 后端未严格使用 Schema

- **文件**：后端 `src/job_agent_os/api/v1/sessions.py` 第 51-61 行、前端 `frontend/src/types/session.ts` 第 57-61 行
- **描述**：后端返回的 `result` 来自 service 返回值，未显式使用 `SessionMessageResponse` schema 序列化。如果 service 返回的结构与 schema 不一致，前端类型检查不会报错但运行时可能出错。
- **修复建议**：后端显式使用 `SessionMessageResponse` 序列化返回值。

### 13.7 【P3】TokenUsageStats by_day 后端始终返回空数组

- **文件**：后端 `src/job_agent_os/api/v1/monitoring.py` 第 94 行、前端 `frontend/src/lib/api/monitoring.ts` 第 14 行
- **描述**：后端实际返回 `"by_day": []`（空数组），前端 `DailyUsageChart` 组件将永远收到空数据。
- **修复建议**：后端实现按日聚合查询。

### 13.8 【P3】初始加载时 Token 未加载的竞态条件

- **文件**：`frontend/src/lib/api/client.ts`、`frontend/src/stores/auth-store.ts`、`frontend/src/app/providers.tsx`
- **描述**：`accessToken` 模块变量初始为 `null`，`hydrate()` 在 `useEffect` 中调用。如果任何 API 调用在 `hydrate()` 执行前发起，Authorization 头将为空。虽然 layout 通过 `isHydrated` 守卫阻止了大部分情况，但 `NotificationBell` 等组件的 API 调用可能提前触发。
- **修复建议**：确保所有 API 调用都在 hydration 完成后发起。

---

## 十四、死代码与空实现汇总

### 完全未集成的 Harness 组件

| 组件 | 文件 | 状态 |
|------|------|------|
| BudgetController | `harness/budget_controller.py` | 从未被调用 |
| GuardRailChain + 4个 Guard | `harness/guard_rails.py` | 从未被调用 |
| RecoveryManager | `harness/recovery_manager.py` | 从未被调用 |
| TraceManager | `harness/trace_manager.py` | 从未被调用 |
| execution_engine.py | `harness/execution_engine.py` | 空文件，仅 docstring |

### Agent 层死代码

| 方法/变量 | 文件 | 行号 | 状态 |
|-----------|------|------|------|
| `_get_structured_llm` | `agents/base.py` | 72-79 | 从未被调用 |
| `_extract_tool_results` | `agents/base.py` | 170-179 | 从未被调用，且逻辑有缺陷 |
| `_llm_fallback` | `agents/base.py` | 43 | 从未在 execute 中使用 |

### 空实现的服务和路由

| 文件 | 描述 |
|------|------|
| `services/resume_service.py` | 仅 2 行 docstring，无实现 |
| `services/user_service.py` | 仅 2 行 docstring，无实现 |
| `api/v1/prompts.py` | 5 行，注册空路由器无端点 |
| `api/v1/interview.py` 第 74-127 行 | `_generate_questions_background` 为占位实现 |

---

## 十五、修复优先级建议

### P0 — 必须立即修复（8项）

1. **补全 tracker_node 的 return 语句** — `graph/nodes.py` 第 67-69 行，投递管理功能完全不工作
2. **修复 resume_agent 空结果导致 Supervisor 无限循环** — `agents/resume_agent.py` 第 97 行
3. **为 search_results 等 list 字段添加 reducer** — `graph/state.py` 第 47-69 行，防止数据覆盖
4. **集成 Harness 保护机制到 runtime.py** — `harness/runtime.py` 第 53-55 行
5. **修复 session_service 不存在的方法调用** — `services/approval_service.py` 第 121 行
6. **修复后台任务使用已关闭的数据库会话** — `services/approval_service.py` 第 120-121 行
7. **修复 CORS 配置** — `api/middleware.py` 第 68-74 行，限制 allow_origins
8. **修复 JWT 默认密钥** — `settings.py` 第 103 行，启动时检查

### P1 — 高优先级（12项）

9. 修复 ToolMessage 缺少 name 属性 — `agents/base.py` 第 141-143 行
10. 启用 Fallback LLM 降级机制 — `agents/base.py` 第 87 行
11. 完善 ReAct 循环异常处理 — `agents/base.py` 第 110-115 行
12. 修复 Supervisor JSON 解析 — `agents/supervisor.py` 第 130-149 行
13. 实现生产环境 checkpointer — `graph/checkpointer.py` 第 16-20 行
14. 配置 interrupt_before 启用 HITL — `graph/main_graph.py` 第 89 行
15. 修复 resumes.py 依赖注入方式 — `api/v1/resumes.py` 多处
16. 修复后台任务引用未保持 — `services/session_service.py`、`services/approval_service.py`
17. 修复 session_service 状态检查不一致 — 第 287 行 `"error"` → `"failed"`
18. 添加 token 类型校验 — `api/deps.py` 第 34 行
19. 修复 Bearer token 解析 — `api/deps.py` 第 33 行
20. 修复前端错误处理静默吞错 — `jobs/page.tsx`、`kanban/page.tsx`、`resume/page.tsx`
21. 添加 API 客户端超时处理 — `frontend/src/lib/api/client.ts`
22. 统一 InterviewQuestion 类型定义 — `types/session.ts`、`lib/api/interview.ts`
23. 修复 Resume 上传绕过统一 API 客户端 — `frontend/src/lib/api/resumes.ts`
24. 修复 cancel_session 不会实际取消 — `harness/runtime.py` 第 71-76 行
25. 修复 _active_sessions 内存泄漏 — `harness/runtime.py` 第 22 行
26. 修复 RecoveryManager _use_fallback 注入 TypeError — `harness/recovery_manager.py` 第 165 行
27. 修复 TraceManager error_type 计算错误 — `harness/trace_manager.py` 第 112 行

### P2 — 中优先级（18项）

28. 修复 match_agent 模糊技能匹配误匹配 — `agents/match_agent.py` 第 83 行
29. 修复 parse_agent fallback 假置信度 — `agents/parse_agent.py` 第 87-103 行
30. 补全 search_agent platforms_searched 追踪 — `agents/search_agent.py` 第 79-82 行
31. 修复 resume_agent/interview_agent 直接索引 KeyError — 第 41/40 行
32. 修复 tracker_agent 工具注册与 prompt 不一致 — `agents/tracker_agent.py` 第 30 行
33. 修复 tracker_agent 忽略工具调用结果 — `agents/tracker_agent.py` 第 53-85 行
34. 修复 Supervisor 不使用 execute() 问题 — `agents/supervisor.py` 第 256-262 行
35. 修复 flush_to_db 无条件清空日志 — `harness/trace_manager.py` 第 182 行
36. 完善 GuardRailChain OutputValidationGuard — `harness/guard_rails.py` 第 130-137 行
37. 修复 BudgetController._history 无上限 — `harness/budget_controller.py` 第 54 行
38. 修复 RecoveryManager last_error 可能为 None — `harness/recovery_manager.py` 第 172 行
39. 修复 resumes.py 无用查询 — `api/v1/resumes.py` 第 115-117 行
40. 修复 evaluations.py/monitoring.py 绕过服务层 — `api/v1/evaluations.py`、`api/v1/monitoring.py`
41. 修复 days 参数未生效 — `api/v1/evaluations.py`、`api/v1/monitoring.py`
42. 修复 interview.py 内存任务无清理 — `api/v1/interview.py` 第 18 行
43. 修复 approval_service.py 静默吞异常 — 第 122-124 行
44. 修复 auth_service.py register 后重复查询
45. 修复动态排序字段安全风险 — `application_service.py`、`job_service.py`
46. 修复 Application.resume_id 缺少用户归属校验 — `models/application.py`
47. 添加 session_id 外键约束 — 多个模型文件
48. 修复 User 模型 lazy="selectin" N+1 问题 — `models/user.py`
49. 补全 ApprovalResponse/ResumeResponse/JobResponse 缺失字段
50. 修复 db/session.py 自动提交问题 — `db/session.py` 第 50-57 行
51. 修复密码静默截断 — `core/security.py` 第 15、21 行
52. 修复 settings.py lru_cache 阻止配置刷新
53. 验证 embedding_model 名称 — `settings.py` 第 120 行
54. 修复 MemoryStore.get_memory 副作用未持久化 — `memory/store.py` 第 148-150 行
55. 修复 embeddings.py 全局单例未关闭 — `memory/embeddings.py` 第 104-112 行
56. 修复前端轮询无并发保护 — `frontend/src/lib/hooks/useSession.ts`
57. 修复前端 isPolling 不响应式更新 — `frontend/src/lib/hooks/useSession.ts`
58. 修复 ChatPage 状态管理脆弱 — `frontend/src/app/(main)/chat/page.tsx`
59. 修复 ContextPanel TOKEN_BUDGET 硬编码 — `frontend/src/components/chat/ContextPanel.tsx`
60. 修复 ResumeCard catch 完全静默 — `frontend/src/components/resume/ResumeCard.tsx`
61. 修复 KanbanView.statistics 字段未定义
62. 修复 API_BASE 硬编码 — `frontend/next.config.mjs`
63. 修复 Token localStorage XSS 风险 — `frontend/src/lib/api/client.ts`
64. 修复 SessionMessageResponse 未使用 Schema 序列化

### P3 — 低优先级（14项）

65. 统一 JSON 解析逻辑（Supervisor 和各 Agent 重复实现）
66. 删除 edges.py 末尾死代码
67. 修复 budget_controller 未使用的 field 导入
68. 移除 Supervisor 仅捕获第一条用户消息的限制
69. 扩展 intent_agent fallback 关键词列表
70. 修复 prompts.py 空路由
71. 修复 job_service.py 错误码语义不匹配
72. 修复 Application 和 Resume 关系不对称
73. 修复 rag.py 文本分块不感知语言边界
74. 修复 vectorstore.py 使用 raw SQL text 排序
75. 移除 settings.py 未使用的配置子类
76. 修复 TokenUsageStats by_day 始终返回空数组
77. 修复初始加载 Token 未加载竞态条件
78. 修复 isBusy null 冗余检查
79. 修复 useSession.ts NodeJS.Timeout 类型
80. 修复 ResumeUploader eslint 抑制

---

## 附录：问题统计

| 分类 | P0 | P1 | P2 | P3 | 合计 |
|------|----|----|----|----|------|
| 后端 Agent 层 | 2 | 5 | 5 | 2 | 14 |
| 后端 Graph 层 | 1 | 2 | 0 | 1 | 4 |
| 后端 Harness 层 | 1 | 4 | 3 | 0 | 8 |
| 后端 API 层 | 0 | 1 | 4 | 1 | 6 |
| 后端服务层 | 2 | 1 | 4 | 1 | 8 |
| 后端数据模型 | 0 | 0 | 3 | 1 | 4 |
| 后端 Schema | 0 | 0 | 3 | 0 | 3 |
| 后端数据库会话 | 1 | 0 | 1 | 0 | 2 |
| 后端安全 | 2 | 2 | 1 | 1 | 6 |
| 后端配置/Memory | 0 | 0 | 4 | 3 | 7 |
| 前端代码 | 0 | 2 | 5 | 3 | 10 |
| 前后端集成 | 0 | 2 | 4 | 2 | 8 |
| **合计** | **9** | **19** | **37** | **15** | **80** |
