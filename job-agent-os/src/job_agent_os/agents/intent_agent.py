"""Intent Agent - Parse user job search intent using LLM structured output."""

import json
from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState


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


class IntentAgent(BaseAgent):
    """Intent Agent parses user's natural language job search intent.

    Uses LLM with_structured_output for reliable parsing.
    Supports multi-turn conversation context.
    """

    name = "intent"
    required_tools: list[str] = []
    prompt_key = "intent_parse"

    async def execute(self, state: JobAgentState) -> dict:
        """Execute intent parsing with structured output."""
        messages = state.get("messages", [])
        user_input = ""
        if messages:
            last_message = messages[-1]
            if isinstance(last_message, HumanMessage):
                user_input = last_message.content
            elif hasattr(last_message, "content"):
                user_input = str(last_message.content)

        if not user_input:
            return {
                "current_phase": "intent",
                "clarification_needed": True,
                "clarification_question": "请告诉我您的求职意向，例如：地区、企业性质、岗位方向等。",
            }

        # Try structured output first
        try:
            result = await self._parse_with_structured_output(user_input, state)
            return result
        except Exception:
            # Fallback to JSON parsing
            try:
                result = await self._parse_with_json(user_input)
                return result
            except Exception:
                return self._fallback_parse(user_input)

    async def _parse_with_structured_output(self, user_input: str, state: JobAgentState) -> dict:
        """Parse using LLM structured output."""
        structured_llm = self._get_structured_llm(IntentOutput)

        # Build context from conversation history
        history_context = ""
        messages = state.get("messages", [])
        if len(messages) > 1:
            history_context = "对话历史:\n" + "\n".join(
                f"- {m.content}" for m in messages[:-1] if hasattr(m, "content")
            )

        prompt = f"""{history_context}

用户最新输入: {user_input}

请解析用户的求职意向。如果信息不足以进行搜索（缺少地区或岗位方向），设置 clarification_needed=true 并生成追问。"""

        result: IntentOutput = await structured_llm.ainvoke(prompt)

        job_query = {
            "region": result.region,
            "company_type": result.company_type,
            "direction": result.direction,
            "skills": result.skills,
            "salary_min": result.salary_min,
            "salary_max": result.salary_max,
            "education": result.education,
        }

        return {
            "current_phase": "intent",
            "job_query": job_query,
            "clarification_needed": result.clarification_needed,
            "clarification_question": result.clarification_question,
        }

    async def _parse_with_json(self, user_input: str) -> dict:
        """Fallback: parse using JSON response."""
        llm = self._get_llm()
        system_prompt, user_prompt = self._build_prompt(user_input)

        response = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])

        result = self._parse_json_response(response.content)
        return {
            "current_phase": "intent",
            "job_query": result.get("job_query"),
            "clarification_needed": result.get("clarification_needed", False),
            "clarification_question": result.get("clarification_question"),
        }

    def _build_prompt(self, user_input: str) -> tuple[str, str]:
        from job_agent_os.prompts.loader import load_prompt
        return load_prompt(self.prompt_key, {"user_input": user_input})

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            else:
                json_str = content
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            return {"job_query": None, "clarification_needed": True, "clarification_question": "抱歉，我无法理解您的需求，请重新描述。"}

    def _fallback_parse(self, user_input: str) -> dict:
        """Fallback parsing using simple keyword extraction."""
        regions = ["河南", "郑州", "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京"]
        company_types = ["国企", "央企", "民企", "外企", "事业单位", "上市公司"]
        directions = ["Java", "Python", "前端", "后端", "算法", "测试", "运维", "数据", "Go", "C++"]

        job_query = {
            "region": [r for r in regions if r in user_input],
            "company_type": [c for c in company_types if c in user_input],
            "direction": next((d for d in directions if d in user_input), ""),
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
