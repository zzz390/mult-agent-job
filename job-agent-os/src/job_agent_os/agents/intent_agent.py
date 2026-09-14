"""Intent Agent - Parse user job search intent using LLM structured output (ReAct)."""

import json
import logging

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from job_agent_os.agents.base import BaseAgent
from job_agent_os.core.json_utils import extract_json_object
from job_agent_os.graph.state import JobAgentState

logger = logging.getLogger(__name__)


class IntentOutput(BaseModel):
    """Structured output schema for intent parsing."""

    region: list[str] = Field(default_factory=list, description="期望工作地区")
    company_type: list[str] = Field(default_factory=list, description="企业性质")
    direction: str = Field(default="", description="岗位方向")
    skills: list[str] = Field(default_factory=list, description="技能要求")
    salary_min: int | None = Field(default=None, description="最低薪资(K)")
    salary_max: int | None = Field(default=None, description="最高薪资(K)")
    education: str | None = Field(default=None, description="学历要求")
    clarification_needed: bool = Field(default=False, description="是否需要追问")
    clarification_question: str | None = Field(default=None, description="追问问题")


INTENT_SYSTEM_PROMPT = """你是求职意向解析专家。你的任务是从用户的自然语言输入中提取结构化的求职意向。

你需要提取以下信息：
- region: 期望工作地区（如：河南、郑州、北京）
- company_type: 企业性质（如：国企、央企、外企、民企）
- direction: 岗位方向（如：Python、Java、前端、算法）
- skills: 具体技能要求
- salary_min/salary_max: 薪资范围（K为单位）
- education: 学历要求

判断规则：
- 只要用户提供了"地区"和"岗位方向/技能"中的任意一项，就足以进行搜索，不需要追问。
- 只有当用户输入完全无法提取任何有效信息时，才设置 clarification_needed=true。
- "python""java""前端"等应识别为岗位方向(direction)。

请以JSON格式输出解析结果。"""


class IntentAgent(BaseAgent):
    """Intent Agent parses user's natural language job search intent (ReAct mode)."""

    name = "intent"
    system_prompt = INTENT_SYSTEM_PROMPT
    agent_tools: list[str] = []  # Intent agent doesn't need external tools
    max_iterations = 2

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build messages with user's input for intent parsing."""
        user_input = self._extract_user_input(state)

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"用户输入: {user_input}\n\n请解析求职意向，以JSON格式输出。"),
        ]

    async def _prepare_messages(
        self, state: JobAgentState, messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        """Inject recalled long-term preferences into the system prompt.

        Before parsing a new intent, we recall the user's historical job
        preferences from long-term memory so the LLM can disambiguate
        partial inputs (e.g. "还是老地方" -> previously preferred city).
        Failures are non-fatal: memory recall must never block intent parsing.
        """
        user_id = state.get("user_id")
        if not user_id:
            return messages

        try:
            memory_context = await self._recall_preference_context(state)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Memory recall skipped: {e}")
            return messages

        if not memory_context:
            return messages

        # Append memory context to the system message
        enriched = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                enriched.append(SystemMessage(content=msg.content + memory_context))
            else:
                enriched.append(msg)
        return enriched

    async def _recall_preference_context(self, state: JobAgentState) -> str:
        """Recall top historical preference memories for the user."""
        import asyncio
        from uuid import UUID as _UUID

        from job_agent_os.db.session import get_session_factory
        from job_agent_os.memory.store import PostgresMemoryStore

        user_input = self._extract_user_input(state)

        async def _recall() -> str:
            session_factory = get_session_factory()
            async with session_factory() as db:
                store = PostgresMemoryStore(db)
                memories = await store.search_memories(
                    user_id=_UUID(str(state["user_id"])),
                    query=user_input,
                    category="preference",
                    top_k=3,
                )
                if not memories:
                    return ""
                pref_texts = [f"- {m.content_text}" for m in memories if m.content_text]
                if not pref_texts:
                    return ""
                return "\n\n用户历史偏好（供参考，仅在用户输入不明确时参考）：\n" + "\n".join(pref_texts)

        return await asyncio.wait_for(_recall(), timeout=3.0)

    def _extract_user_input(self, state: JobAgentState) -> str:
        """Extract the latest user input text from state."""
        messages = state.get("messages", [])
        user_input = ""
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, HumanMessage):
                user_input = last_msg.content
            elif hasattr(last_msg, "content"):
                user_input = str(last_msg.content)

        # Also check task_instruction from Supervisor
        task = self._get_task_instruction(state)
        if task and not user_input:
            user_input = task

        return user_input or "（用户未提供输入）"

    def _parse_final_output(self, messages: list[BaseMessage], state: JobAgentState) -> dict:
        """Parse LLM output into structured intent."""
        content = self._get_last_ai_content(messages)

        if not content:
            return {
                "current_phase": "intent",
                "clarification_needed": True,
                "clarification_question": "请告诉我您的求职意向，例如：地区、企业性质、岗位方向等。",
            }

        # Try to parse JSON from LLM response
        try:
            result = self._extract_json(content)
            job_query = {
                "region": result.get("region", []),
                "company_type": result.get("company_type", []),
                "direction": result.get("direction", ""),
                "skills": result.get("skills", []),
                "salary_min": result.get("salary_min"),
                "salary_max": result.get("salary_max"),
                "education": result.get("education"),
            }
            return {
                "current_phase": "intent",
                "job_query": job_query,
                "clarification_needed": result.get("clarification_needed", False),
                "clarification_question": result.get("clarification_question"),
            }
        except (json.JSONDecodeError, KeyError, ValueError):
            # Fallback: keyword extraction
            return self._fallback_parse(content)

    def _extract_json(self, content: str) -> dict:
        """Extract JSON from LLM response text."""
        return extract_json_object(content)

    def _fallback_parse(self, user_input: str) -> dict:
        """Fallback parsing using simple keyword extraction (case-insensitive).

        Keyword lists are loaded from configs/intent_keywords.yaml (cached),
        so coverage can be extended without code changes.
        """
        from job_agent_os.core.config_loader import load_intent_keywords

        keywords = load_intent_keywords()
        regions = keywords["regions"]
        company_types = keywords["company_types"]
        directions = keywords["directions"]

        input_lower = user_input.lower()

        job_query = {
            "region": [r for r in regions if r in user_input],
            "company_type": [c for c in company_types if c in user_input],
            "direction": next((d for d in directions if d.lower() in input_lower), ""),
            "skills": [],
            "salary_min": None,
            "salary_max": None,
            "education": None,
        }

        has_region = bool(job_query["region"])
        has_direction = bool(job_query["direction"])

        if not has_region and not has_direction:
            return {
                "current_phase": "intent",
                "job_query": None,
                "clarification_needed": True,
                "clarification_question": "请告诉我您期望的工作地区和岗位方向。",
            }

        return {
            "current_phase": "intent",
            "job_query": job_query,
            "clarification_needed": False,
            "clarification_question": None,
        }


# Singleton instance
intent_agent = IntentAgent()
