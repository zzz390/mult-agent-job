"""Supervisor Agent - Dynamic task routing via LLM structured output.

The Supervisor is the central orchestrator that:
1. Observes the current state (what has been done, what data exists)
2. Uses LLM with structured output to decide which specialist agent to call next
3. Loops until the overall task is complete
"""

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState

logger = logging.getLogger(__name__)

# Agents available for routing
AVAILABLE_AGENTS = [
    "intent",
    "search",
    "web_search",
    "parse",
    "match",
    "resume",
    "interview",
    "tracker",
]


class SupervisorDecision(BaseModel):
    """Supervisor's routing decision (structured output from LLM)."""

    next_agent: str = Field(
        description="下一个要调用的 Agent 名称，必须是以下之一: intent, search, web_search, parse, match, resume, interview, tracker, __end__"
    )
    task_instruction: str = Field(
        description="给该 Agent 的具体任务指令，描述它需要完成什么"
    )
    reasoning: str = Field(
        description="为什么选择这个 Agent（简要推理过程）"
    )
    is_finished: bool = Field(
        default=False,
        description="整体求职任务是否已全部完成"
    )
    final_message: str | None = Field(
        default=None,
        description="任务完成时给用户的总结消息"
    )


SUPERVISOR_SYSTEM_PROMPT = """你是一个智能求职系统的总调度 Supervisor。
你的职责是根据用户的求职意图和当前系统状态，动态决定下一步调用哪个专业 Agent。

## 可用 Agent 及其职责：
- **intent**: 意图解析 Agent — 解析用户自然语言中的求职意向（地区、企业类型、岗位方向、技能等）
- **search**: 岗位搜索 Agent — 从数据库和外部招聘平台搜索匹配岗位
- **web_search**: 官网搜索 Agent — 当数据库无结果时，搜索目标企业官网招聘信息并入库
- **parse**: JD解析 Agent — 将原始岗位描述结构化为标准格式（技能、学历、职责等）
- **match**: 匹配评分 Agent — 对候选岗位进行技能匹配、评分排序
- **resume**: 简历优化 Agent — 针对目标岗位优化用户简历
- **interview**: 面试准备 Agent — 生成技术面试题和行为面试题
- **tracker**: 投递管理 Agent — 创建投递记录、初始化看板状态

## 决策规则（按优先级）：
1. 如果 job_query 为空（用户意图未解析），必须先调 intent
2. 如果 search_results 为空且未搜索过，调 search
3. 如果 search 返回 0 结果，调 web_search 从官网补充数据
4. 如果有搜索结果但 parsed_jobs 为空，调 parse
5. 如果有解析结果但 match_results 为空，调 match
6. 匹配完成后，依次调 resume → interview → tracker
7. 所有步骤完成后，设 next_agent="__end__" 且 is_finished=true

## 重要约束：
- 每次只选一个 Agent
- 不要跳过必要步骤（如未搜索就直接匹配）
- 如果某步骤已有结果（如 match_results 非空），不要重复执行
- 当所有核心步骤（intent→search→parse→match→resume→interview→tracker）完成后才设 is_finished=true

## 输出格式（严格JSON，不要输出其他内容）：
```json
{
  "next_agent": "agent名称或__end__",
  "task_instruction": "给该Agent的具体任务指令",
  "reasoning": "为什么选择这个Agent",
  "is_finished": false,
  "final_message": null
}
```
"""


class SupervisorAgent(BaseAgent):
    """Supervisor Agent for dynamic task routing."""

    name = "supervisor"
    system_prompt = SUPERVISOR_SYSTEM_PROMPT
    agent_tools: list[str] = []  # Supervisor doesn't call tools directly

    async def decide(self, state: JobAgentState) -> SupervisorDecision:
        """Use LLM to decide the next agent (JSON text output, no tool_choice)."""
        llm = self._get_llm()
        context = self._build_context_summary(state)

        try:
            response = await llm.ainvoke([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=f"## 当前系统状态：\n{context}\n\n请决定下一步操作，严格按JSON格式输出。"),
            ])

            # Parse JSON from LLM text response
            decision = self._parse_decision_json(response.content)

            # Validate the decision
            if decision.next_agent not in AVAILABLE_AGENTS and decision.next_agent != "__end__":
                logger.warning(f"Supervisor returned invalid agent: {decision.next_agent}, defaulting to __end__")
                decision.next_agent = "__end__"
                decision.is_finished = True

            return decision

        except Exception as e:
            logger.error(f"Supervisor decision failed: {e}")
            # Fallback: determine next step by state inspection
            return self._fallback_decision(state)

    def _parse_decision_json(self, content: str) -> SupervisorDecision:
        """Parse SupervisorDecision from LLM text response."""
        # Use regex to robustly extract the JSON object from response.
        # re.DOTALL ensures newlines inside braces are matched.
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON found in response: {content[:200]}")

        json_str = match.group(0).strip()
        data = json.loads(json_str)
        return SupervisorDecision(
            next_agent=data.get("next_agent", "__end__"),
            task_instruction=data.get("task_instruction", ""),
            reasoning=data.get("reasoning", ""),
            is_finished=data.get("is_finished", False),
            final_message=data.get("final_message"),
        )

    def _build_context_summary(self, state: JobAgentState) -> str:
        """Build a concise summary of current state for the Supervisor LLM."""
        job_query = state.get("job_query")
        search_results = state.get("search_results", [])
        parsed_jobs = state.get("parsed_jobs", [])
        match_results = state.get("match_results", [])
        optimized_resume = state.get("optimized_resume")
        interview_questions = state.get("interview_questions", [])
        applications = state.get("applications", [])
        execution_order = state.get("agent_execution_order", [])
        clarification_needed = state.get("clarification_needed", False)

        # Get user's original intent from all HumanMessage contents
        messages = state.get("messages", [])
        user_intents = [
            msg.content for msg in messages if isinstance(msg, HumanMessage)
        ]
        user_intent = " | ".join(user_intents) if user_intents else ""

        parts = [
            f"用户原始输入: \"{user_intent}\"",
            f"已执行的Agent顺序: {execution_order}",
            f"意图解析(job_query): {'已完成 - ' + json.dumps(job_query, ensure_ascii=False) if job_query else '未完成'}",
            f"需要追问: {'是' if clarification_needed else '否'}",
            f"搜索结果: {len(search_results)} 条",
            f"JD解析: {len(parsed_jobs)} 条已结构化",
            f"匹配结果: {len(match_results)} 条已评分",
            f"简历优化: {'已完成' if optimized_resume else '未完成'}",
            f"面试题: {len(interview_questions)} 道已生成",
            f"投递记录: {len(applications)} 条已创建",
        ]

        return "\n".join(parts)

    def _fallback_decision(self, state: JobAgentState) -> SupervisorDecision:
        """Rule-based fallback when LLM decision fails."""
        if not state.get("job_query"):
            return SupervisorDecision(
                next_agent="intent",
                task_instruction="解析用户的求职意向",
                reasoning="job_query 为空，需要先解析意图",
            )

        if not state.get("search_results"):
            execution_order = state.get("agent_execution_order", [])
            if "search" in execution_order:
                return SupervisorDecision(
                    next_agent="web_search",
                    task_instruction="数据库和平台搜索无结果，请从企业官网搜索招聘信息",
                    reasoning="search 已执行但无结果，需要 web_search 补充",
                )
            return SupervisorDecision(
                next_agent="search",
                task_instruction="根据解析出的求职意向搜索匹配岗位",
                reasoning="意图已解析但尚未搜索",
            )

        if not state.get("parsed_jobs"):
            return SupervisorDecision(
                next_agent="parse",
                task_instruction="将搜索到的岗位原始数据结构化为标准JD格式",
                reasoning="有搜索结果但未解析",
            )

        if not state.get("match_results"):
            return SupervisorDecision(
                next_agent="match",
                task_instruction="对解析后的岗位进行匹配评分和排序",
                reasoning="有解析结果但未匹配",
            )

        if not state.get("optimized_resume"):
            return SupervisorDecision(
                next_agent="resume",
                task_instruction="针对匹配到的目标岗位优化用户简历",
                reasoning="匹配完成，进行简历优化",
            )

        if not state.get("interview_questions"):
            return SupervisorDecision(
                next_agent="interview",
                task_instruction="根据目标岗位生成面试题",
                reasoning="简历优化完成，准备面试",
            )

        if not state.get("applications"):
            return SupervisorDecision(
                next_agent="tracker",
                task_instruction="为匹配的岗位创建投递记录",
                reasoning="面试准备完成，创建投递",
            )

        return SupervisorDecision(
            next_agent="__end__",
            task_instruction="",
            reasoning="所有步骤已完成",
            is_finished=True,
            final_message="求职全流程已完成：意图解析 → 岗位搜索 → JD解析 → 匹配评分 → 简历优化 → 面试准备 → 投递创建",
        )

    # --- Abstract method implementations (not used for Supervisor) ---

    def _build_initial_messages(self, state: JobAgentState) -> list:
        """Not used — Supervisor uses decide() instead of execute()."""
        return []

    def _parse_final_output(self, messages: list, state: JobAgentState) -> dict:
        """Not used — Supervisor uses decide() instead of execute()."""
        return {}

    async def execute(self, state: JobAgentState) -> dict:
        """Supervisor does not use execute() — it uses decide()."""
        raise NotImplementedError("Supervisor uses route() method, not execute()")


# Singleton instance
supervisor_agent = SupervisorAgent()
