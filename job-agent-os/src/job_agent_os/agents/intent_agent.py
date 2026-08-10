"""Intent Agent - Parse user job search intent using LLM structured output (ReAct)."""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
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

        if not user_input:
            user_input = "（用户未提供输入）"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"用户输入: {user_input}\n\n请解析求职意向，以JSON格式输出。"),
        ]

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
        except (json.JSONDecodeError, KeyError):
            # Fallback: keyword extraction
            return self._fallback_parse(content)

    def _extract_json(self, content: str) -> dict:
        """Extract JSON from LLM response text."""
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        elif "{" in content:
            json_str = content[content.index("{"):content.rindex("}") + 1]
        else:
            json_str = content
        return json.loads(json_str.strip())

    def _fallback_parse(self, user_input: str) -> dict:
        """Fallback parsing using simple keyword extraction (case-insensitive)."""
        # NOTE: These keyword lists are hardcoded for common Chinese regions/directions.
        # TODO: Expand coverage to more regions, company types, and job directions.
        #       Consider loading from a config file or database for maintainability.
        regions = ["河南", "郑州", "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "洛阳", "开封"]
        company_types = ["国企", "央企", "民企", "外企", "事业单位", "上市公司"]
        directions = ["Java", "Python", "前端", "后端", "算法", "测试", "运维", "数据", "Go", "C++", "AI", "大数据"]

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
