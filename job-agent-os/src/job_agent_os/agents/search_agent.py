"""Search Agent - Search jobs from database and external platforms (ReAct mode).

Strategy:
1. Query the local database first
2. If insufficient results, search external platforms
3. Deduplicate and save new results to database
"""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState

SEARCH_SYSTEM_PROMPT = """你是岗位搜索专家。根据用户的求职意向，搜索匹配的岗位。

你可以使用以下工具：
1. query_jobs_db - 从数据库查询已有岗位（支持按关键词、地区、企业类型筛选）
2. boss_search - 在BOSS直聘平台搜索岗位
3. guopin_search - 在国聘平台搜索国企/央企岗位
4. niuke_search - 在牛客平台搜索校招岗位
5. dedup - 对岗位列表按内容哈希去重
6. save_jobs_db - 将新岗位批量存入数据库

搜索策略：
1. 先用 query_jobs_db 查询数据库，看是否有足够的匹配岗位
2. 如果数据库结果不足（少于5条），再调用外部平台搜索
3. 对外部搜索结果调用 dedup 去重
4. 将去重后的新岗位调用 save_jobs_db 存入数据库

最终输出：将所有搜索到的岗位以JSON数组格式输出。"""


class SearchAgent(BaseAgent):
    """Search Agent searches for jobs using database + external platforms (ReAct)."""

    name = "search"
    system_prompt = SEARCH_SYSTEM_PROMPT
    agent_tools = ["query_jobs_db", "boss_search", "guopin_search", "niuke_search", "dedup", "save_jobs_db"]
    max_iterations = 6

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build search task from job_query."""
        job_query = state.get("job_query", {})
        task = self._get_task_instruction(state)

        query_desc = json.dumps(job_query, ensure_ascii=False) if job_query else "未指定"
        content = f"请搜索符合以下求职条件的岗位：\n{query_desc}"
        if task:
            content += f"\n\nSupervisor 补充指令：{task}"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

    def _parse_final_output(self, messages: list[BaseMessage], state: JobAgentState) -> dict:
        """Extract search results from tool call outputs."""
        all_jobs: list[dict] = []
        errors: list[dict] = []
        platforms_searched: list[str] = []

        # Collect results from all tool messages
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            tool_name = getattr(msg, "name", "")
            try:
                data = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                continue

            # Handle error responses
            if isinstance(data, dict) and "error" in data:
                errors.append({"tool": tool_name or "unknown", "error": data["error"]})
                continue

            # query_jobs_db returns list of jobs
            if isinstance(data, list):
                all_jobs.extend(data)
                # Map tool name to platform name
                platform_map = {
                    "query_jobs_db": "database",
                    "boss_search": "boss",
                    "guopin_search": "guopin",
                    "niuke_search": "niuke",
                }
                platform = platform_map.get(tool_name)
                if platform and platform not in platforms_searched:
                    platforms_searched.append(platform)
            elif isinstance(data, int):
                # save_jobs_db returns count
                pass

        # Also try to parse from the final AI message (in case LLM summarized)
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

        return {
            "current_phase": "search",
            "search_results": all_jobs,
            "search_errors": errors,
            "platforms_searched": platforms_searched or ["none"],
        }


# Singleton instance
search_agent = SearchAgent()
