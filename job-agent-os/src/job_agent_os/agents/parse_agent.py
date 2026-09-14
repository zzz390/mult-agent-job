"""Parse Agent - Structure raw job descriptions using LLM (concurrent mode).

Issue #9: Previously this agent relied on the ReAct loop to call
jd_structurer one job at a time — N jobs meant N serial LLM round trips
(30-60s for 20 results). It now structures jobs directly with
asyncio.gather + a semaphore for bounded concurrency.
"""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.core.json_utils import extract_json_array
from job_agent_os.graph.state import JobAgentState

PARSE_SYSTEM_PROMPT = """你是JD（岗位描述）结构化解析专家。你的任务是将原始岗位数据结构化为标准格式。

你可以使用以下工具：
1. jd_structurer - 使用LLM将原始岗位描述文本结构化为标准JD格式（含技能、学历、职责等）
2. html_parser - 如果岗位有source_url但缺少描述，可抓取网页获取完整JD文本

工作策略：
1. 对每个搜索结果中的岗位，检查是否有足够的 raw_description
2. 如果缺少描述但有 source_url，先用 html_parser 抓取
3. 对每个岗位调用 jd_structurer 进行结构化
4. 只保留 parse_confidence >= 0.6 的结果

最终输出：将结构化后的岗位以JSON数组格式输出。每个岗位应包含：
title, company, location, salary, skills_required, education, responsibilities, parse_confidence"""


class ParseAgent(BaseAgent):
    """Parse Agent structures raw job data into standard JD format.

    Primary path: direct concurrent structuring via structure_jds_parallel
    (deterministic, fast). The ReAct loop remains as a fallback.
    """

    name = "parse"
    system_prompt = PARSE_SYSTEM_PROMPT
    agent_tools = ["jd_structurer", "html_parser"]
    max_iterations = 6

    # Max jobs structured in one pass (kept in sync with previous behavior)
    max_jobs_per_run = 15

    async def execute(self, state: JobAgentState) -> dict:
        """Structure search results concurrently (issue #9).

        Falls back to the classic ReAct loop only if the direct path fails.
        """
        search_results = state.get("search_results", [])
        jobs_to_parse = search_results[: self.max_jobs_per_run]

        if jobs_to_parse:
            try:
                from job_agent_os.tools.parse.jd_structurer import structure_jds_parallel

                parsed_jobs, parse_failures = await structure_jds_parallel(jobs_to_parse)
                return {
                    "current_phase": "parse",
                    "parsed_jobs": parsed_jobs,
                    "parse_failures": parse_failures,
                }
            except Exception:  # noqa: BLE001 - keep ReAct path as safety net
                pass

        return await super().execute(state)

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build parse task from search_results."""
        search_results = state.get("search_results", [])
        task = self._get_task_instruction(state)

        # Limit to avoid overly long prompts
        jobs_to_parse = search_results[:15]
        jobs_summary = json.dumps(jobs_to_parse, ensure_ascii=False, default=str)

        content = f"请将以下 {len(jobs_to_parse)} 个原始岗位数据结构化为标准JD格式：\n{jobs_summary}"
        if task:
            content += f"\n\nSupervisor 补充指令：{task}"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

    def _parse_final_output(self, messages: list[BaseMessage], state: JobAgentState) -> dict:
        """Extract parsed jobs from tool outputs and AI response."""
        parsed_jobs: list[dict] = []
        parse_failures: list[str] = []

        # Collect from jd_structurer tool messages
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            try:
                data = json.loads(msg.content)
                if isinstance(data, dict) and data.get("title"):
                    if data.get("parse_confidence", 0) >= 0.6:
                        parsed_jobs.append(data)
                    else:
                        parse_failures.append(data.get("source_url", "unknown"))
                elif isinstance(data, dict) and "error" in data:
                    parse_failures.append("tool_error")
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: parse from AI final message
        if not parsed_jobs:
            content = self._get_last_ai_content(messages)
            if content:
                try:
                    parsed = extract_json_array(content)
                    if isinstance(parsed, list):
                        parsed_jobs = [j for j in parsed if isinstance(j, dict) and j.get("title")]
                except ValueError:
                    pass

        # If still nothing, pass through search_results as-is (basic structure)
        if not parsed_jobs:
            search_results = state.get("search_results", [])
            parsed_jobs = [
                {
                    "title": j.get("title", ""),
                    "company": j.get("company", ""),
                    "location": j.get("location"),
                    "salary": j.get("salary"),
                    "skills_required": j.get("skills_required", []),
                    "education": j.get("education"),
                    "source_url": j.get("source_url", ""),
                    "source_platform": j.get("source_platform", ""),
                    "parse_confidence": 0.3,  # Low confidence — below 0.6 threshold
                    "parse_note": "fallback_unparsed",
                }
                for j in search_results
                if j.get("title")
            ]

        return {
            "current_phase": "parse",
            "parsed_jobs": parsed_jobs,
            "parse_failures": parse_failures,
        }


# Singleton instance
parse_agent = ParseAgent()
