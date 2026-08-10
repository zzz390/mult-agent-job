"""Web Search Agent - Search company official career sites (ReAct mode).

When database and platform searches return insufficient results,
this agent uses LLM to identify target companies and searches their career sites.
"""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState

WEB_SEARCH_SYSTEM_PROMPT = """你是企业官网招聘信息搜索专家。当数据库和招聘平台搜索不到足够岗位时，你负责从企业官网获取招聘信息。

你可以使用以下工具：
1. html_parser - 抓取指定URL网页并提取正文文本
2. query_jobs_db - 查询数据库确认是否已有该企业的岗位
3. save_jobs_db - 将新发现的岗位存入数据库
4. dedup - 对岗位列表去重

工作策略：
1. 根据用户的求职条件（地区、企业类型、方向），列出可能正在招聘的目标企业
2. 尝试访问这些企业的招聘页面（常见URL模式：hr.company.com、recruit.company.com）
3. 从页面中提取岗位信息
4. 如果无法直接爬取，基于你对这些企业的了解，生成合理的在招岗位信息
5. 将所有岗位调用 save_jobs_db 存入数据库

最终输出：将搜索/生成的岗位以JSON数组格式输出，每个岗位包含 title、company、company_type、location、salary、skills_required、raw_description 字段。"""


class WebSearchAgent(BaseAgent):
    """Web Search Agent finds jobs from company career sites (ReAct)."""

    name = "web_search"
    system_prompt = WEB_SEARCH_SYSTEM_PROMPT
    agent_tools = ["html_parser", "query_jobs_db", "save_jobs_db", "dedup"]
    max_iterations = 6

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build web search task from job_query."""
        job_query = state.get("job_query", {})
        task = self._get_task_instruction(state)

        query_desc = json.dumps(job_query, ensure_ascii=False) if job_query else "未指定"
        content = (
            f"数据库和平台搜索未找到足够岗位。请从企业官网搜索以下条件的招聘信息：\n{query_desc}"
        )
        if task:
            content += f"\n\nSupervisor 补充指令：{task}"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

    def _parse_final_output(self, messages: list[BaseMessage], state: JobAgentState) -> dict:
        """Extract web search results."""
        all_jobs: list[dict] = []

        # Collect from tool messages (save_jobs_db results, html_parser results)
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            try:
                data = json.loads(msg.content)
                if isinstance(data, list):
                    all_jobs.extend(data)
            except (json.JSONDecodeError, TypeError):
                continue

        # Parse from final AI message
        if not all_jobs:
            content = self._get_last_ai_content(messages)
            if content:
                try:
                    if "[" in content:
                        json_str = content[content.index("["):content.rindex("]") + 1]
                        parsed = json.loads(json_str)
                        if isinstance(parsed, list):
                            all_jobs = parsed
                except (json.JSONDecodeError, ValueError):
                    pass

        # Merge platforms_searched with existing state value (dedup, preserve order)
        existing_platforms = state.get("platforms_searched", [])
        merged_platforms = list(dict.fromkeys(existing_platforms + ["web_career_sites"]))

        return {
            "current_phase": "web_search",
            "search_results": all_jobs,
            "search_errors": [],
            "platforms_searched": merged_platforms,
        }


# Singleton instance
web_search_agent = WebSearchAgent()
