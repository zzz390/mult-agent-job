"""Supervisor Agent - deterministic routing with LLM exception replanning.

The Supervisor is the central orchestrator that:
1. Observes the current state (what has been done, what data exists)
2. Routes the normal pipeline from explicit state transitions
3. Uses structured LLM output only when an error or unknown mode needs replanning
4. Loops until the overall task is complete
"""

import json
import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from job_agent_os.agents.base import BaseAgent
from job_agent_os.core.json_utils import extract_json_object
from job_agent_os.graph.contracts import RouteName
from job_agent_os.graph.state import JobAgentState

logger = logging.getLogger(__name__)

class SupervisorDecision(BaseModel):
    """Supervisor's routing decision (structured output from LLM)."""

    next_agent: RouteName = Field(
        description="下一个要调用的 Agent 名称，必须是以下之一: intent, search, match, resume, interview, __end__"
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
- **search**: 岗位搜索 Agent — 从数据库和外部招聘平台搜索匹配岗位；搜索结果为空时会自动降级到企业官网搜索，并自动完成 JD 结构化（无需再单独调 web_search / parse）
- **match**: 匹配评分 Agent — 对候选岗位进行技能匹配、评分排序
- **resume**: 简历优化 Agent — 针对目标岗位优化用户简历
- **interview**: 面试准备 Agent — 生成技术面试题和行为面试题，并自动为匹配岗位创建投递记录（无需再单独调 tracker）

## 决策规则（按优先级）：
1. 如果 job_query 为空（用户意图未解析），必须先调 intent
2. 如果 clarification_needed 为 true，设 next_agent="__end__" 且 is_finished=true，在 final_message 中输出追问问题
3. 如果 search_results 为空且未搜索过，调 search
4. 如果有解析结果（parsed_jobs 非空）但 match_results 为空，调 match
5. 匹配完成后，依次调 resume → interview
6. 所有步骤完成后，设 next_agent="__end__" 且 is_finished=true

## 重要约束：
- 每次只选一个 Agent
- 不要跳过必要步骤（如未搜索就直接匹配）
- 如果某步骤已有结果（如 match_results 非空），不要重复执行
- 不要选择 web_search / parse / tracker，它们的职责已分别并入 search 和 interview
- 当所有核心步骤（intent→search→match→resume→interview）完成后才设 is_finished=true

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
        """Route deterministically unless the workflow genuinely needs replanning.

        The normal workflow is a state machine, so spending one LLM call after
        every specialist adds cost and route variance without adding useful
        judgment. LLM planning is reserved for an error state or an unknown
        execution mode; even then deterministic rules remain the final fallback.
        """
        completed = self._mode_completion_decision(state)
        if completed is not None:
            return completed

        if not self._needs_llm_replan(state):
            return self._fallback_decision(state)

        try:
            decision = await self._decide_with_llm(state, use_fallback=False)
            return self._enforce_mode_boundary(state, decision)
        except Exception as e:
            logger.warning(f"Supervisor primary LLM failed: {e}; retrying with fallback LLM")

        try:
            decision = await self._decide_with_llm(state, use_fallback=True)
            return self._enforce_mode_boundary(state, decision)
        except Exception as e:
            logger.error(f"Both supervisor LLMs failed: {e}")
            # Final fallback: determine next step by state inspection
            return self._fallback_decision(state)

    @staticmethod
    def _needs_llm_replan(state: JobAgentState) -> bool:
        """Return whether normal deterministic routing is insufficient."""
        known_modes = {
            "full",
            "search_only",
            "match_only",
            "resume_only",
            "interview_only",
        }
        return bool(state.get("error_state")) or state.get("mode", "full") not in known_modes

    @staticmethod
    def _mode_completion_decision(
        state: JobAgentState,
    ) -> SupervisorDecision | None:
        mode = state.get("mode", "full")
        requirements = {
            "search_only": bool(state.get("parsed_jobs")),
            "match_only": bool(state.get("match_results")),
            "resume_only": bool(state.get("optimized_resume")),
            "interview_only": bool(state.get("interview_questions")),
        }
        if mode in requirements and requirements[mode]:
            return SupervisorDecision(
                next_agent="__end__",
                task_instruction="",
                reasoning=f"{mode} requested stage is complete",
                is_finished=True,
                final_message=f"{mode} 任务已完成。",
            )
        return None

    def _enforce_mode_boundary(
        self, state: JobAgentState, decision: SupervisorDecision
    ) -> SupervisorDecision:
        """Prevent an LLM decision from running beyond the requested mode."""
        mode = state.get("mode", "full")
        target_stage = {
            "search_only": 1,
            "match_only": 2,
            "resume_only": 3,
            "interview_only": 4,
            "full": 4,
        }.get(mode, 4)
        agent_stage = {
            "intent": 0,
            "search": 1,
            "match": 2,
            "resume": 3,
            "interview": 4,
        }
        if decision.next_agent == "__end__" or agent_stage.get(
            decision.next_agent, 99
        ) > target_stage:
            return self._fallback_decision(state)
        return decision

    async def _decide_with_llm(self, state: JobAgentState, use_fallback: bool) -> SupervisorDecision:
        """Single LLM decision attempt (JSON text output, no tool_choice)."""
        llm = self._get_llm(use_fallback=use_fallback)
        context = self._build_context_summary(state)

        response = await llm.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"## 当前系统状态：\n{context}\n\n请决定下一步操作，严格按JSON格式输出。"),
        ])

        # Parse JSON from LLM text response
        content = (
            response.content
            if isinstance(response.content, str)
            else json.dumps(response.content, ensure_ascii=False, default=str)
        )
        decision = self._parse_decision_json(content)

        return decision

    def _parse_decision_json(self, content: str) -> SupervisorDecision:
        """Parse SupervisorDecision from LLM text response."""
        data = extract_json_object(content)
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
        user_intents = [str(msg.content) for msg in messages if isinstance(msg, HumanMessage)]
        user_intent = " | ".join(user_intents) if user_intents else ""

        parts = [
            f"用户原始输入: \"{user_intent}\"",
            f"执行模式: {state.get('mode', 'full')}",
            f"指定平台: {state.get('requested_platforms', [])}",
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
        """Rule-based fallback when LLM decision fails.

        Streamlined pipeline (issue #2): web_search/parse are embedded in
        search, tracker is embedded in interview.
        """
        # Intent can return a partial job_query together with a clarification
        # request. The pause must win over every data-presence check.
        if state.get("clarification_needed"):
            return SupervisorDecision(
                next_agent="__end__",
                task_instruction="",
                reasoning="意图信息不足，需要向用户追问",
                is_finished=True,
                final_message=state.get("clarification_question")
                or "请告诉我您期望的工作地区和岗位方向。",
            )

        if not state.get("job_query"):
            return SupervisorDecision(
                next_agent="intent",
                task_instruction="解析用户的求职意向",
                reasoning="job_query 为空，需要先解析意图",
            )

        if not state.get("search_results"):
            # Guard against infinite search loops when all sources are empty
            execution_order = state.get("agent_execution_order", [])
            if execution_order.count("search") >= 2:
                return SupervisorDecision(
                    next_agent="__end__",
                    task_instruction="",
                    reasoning="搜索多次仍无结果，终止并提示用户",
                    is_finished=True,
                    final_message="很抱歉，数据库、招聘平台和企业官网均未找到匹配的岗位，请尝试调整求职条件后重试。",
                )
            # search 内部会自动降级 web_search 并就地完成 JD 结构化
            return SupervisorDecision(
                next_agent="search",
                task_instruction="根据解析出的求职意向搜索匹配岗位（无结果时自动降级官网搜索并结构化JD）",
                reasoning="意图已解析但尚无搜索结果",
            )

        if not state.get("parsed_jobs"):
            # 正常不会走到这里（search 已内嵌 parse），兜底直接重跑 search
            return SupervisorDecision(
                next_agent="search",
                task_instruction="重新搜索并结构化岗位数据",
                reasoning="有搜索结果但未结构化，重新执行 search 内嵌解析",
            )

        if not state.get("match_results"):
            return SupervisorDecision(
                next_agent="match",
                task_instruction="对解析后的岗位进行匹配评分和排序",
                reasoning="有解析结果但未匹配",
            )

        if not state.get("optimized_resume"):
            if "user_profile" in state and not state.get("user_profile"):
                return SupervisorDecision(
                    next_agent="__end__",
                    task_instruction="",
                    reasoning="没有可用的用户简历，不能进行可信的简历优化",
                    is_finished=True,
                    final_message="岗位匹配已完成；请先上传简历，再继续简历优化。",
                )
            return SupervisorDecision(
                next_agent="resume",
                task_instruction="针对匹配到的目标岗位优化用户简历",
                reasoning="匹配完成，进行简历优化",
            )

        if not state.get("interview_questions"):
            # interview 内部会自动创建投递记录（原 tracker 职责）
            return SupervisorDecision(
                next_agent="interview",
                task_instruction="根据目标岗位生成面试题，并创建投递记录",
                reasoning="简历优化完成，准备面试并创建投递",
            )

        return SupervisorDecision(
            next_agent="__end__",
            task_instruction="",
            reasoning="所有步骤已完成",
            is_finished=True,
            final_message="求职全流程已完成：意图解析 → 岗位搜索（含官网降级+JD结构化） → 匹配评分 → 简历优化 → 面试准备（含投递创建）",
        )

    # --- Abstract method implementations (not used for Supervisor) ---

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Not used — Supervisor uses decide() instead of execute()."""
        return []

    def _parse_final_output(
        self, messages: list[BaseMessage], state: JobAgentState
    ) -> dict[str, Any]:
        """Not used — Supervisor uses decide() instead of execute()."""
        return {}

    async def execute(self, state: JobAgentState) -> dict[str, Any]:
        """Supervisor does not use execute() — it uses decide()."""
        raise NotImplementedError("Supervisor uses route() method, not execute()")


# Singleton instance
supervisor_agent = SupervisorAgent()
