"""Tracker Agent - Create application records and manage kanban (ReAct mode)."""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState

TRACKER_SYSTEM_PROMPT = """你是投递管理专家。你的任务是为匹配到的岗位创建投递记录并初始化看板状态。

你可以使用以下工具：
1. query_jobs_db - 查询数据库确认岗位信息
2. save_jobs_db - 如果需要补充岗位数据

工作内容：
1. 从匹配结果中取出 Top 5 岗位
2. 为每个岗位创建投递记录（状态: pending）
3. 初始化看板状态（所有投递放入 pending 列）
4. 设置跟进提醒（3天后）

最终输出：以JSON格式输出，包含 applications 列表和 kanban_state。"""


class TrackerAgent(BaseAgent):
    """Tracker Agent creates application records (ReAct)."""

    name = "tracker"
    system_prompt = TRACKER_SYSTEM_PROMPT
    agent_tools = ["query_jobs_db", "save_jobs_db"]
    max_iterations = 3

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build tracker task from match_results."""
        match_results = state.get("match_results", [])
        task = self._get_task_instruction(state)

        top_jobs = match_results[:5]
        jobs_summary = json.dumps(
            [{"title": r.get("job", {}).get("title", ""), "company": r.get("job", {}).get("company", ""), "score": r.get("overall_score", 0)} for r in top_jobs],
            ensure_ascii=False,
        )

        content = f"请为以下 {len(top_jobs)} 个匹配岗位创建投递记录：\n{jobs_summary}"
        if task:
            content += f"\n\nSupervisor 补充指令：{task}"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

    def _parse_final_output(self, messages: list[BaseMessage], state: JobAgentState) -> dict:
        """Build application records from match results and tool outputs."""
        match_results = state.get("match_results", [])

        # Extract job info from tool messages to supplement match_results
        tool_jobs: list[dict] = []
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            try:
                data = json.loads(msg.content)
                if isinstance(data, list):
                    # query_jobs_db returns list of jobs with DB info
                    tool_jobs.extend(j for j in data if isinstance(j, dict))
            except (json.JSONDecodeError, TypeError):
                continue

        # Build lookup of job_id -> job info from tool query results
        job_lookup = {}
        for job in tool_jobs:
            if job.get("id"):
                job_lookup[job["id"]] = job

        applications = []
        for result in match_results[:5]:
            job = result.get("job", {})
            # Supplement with tool query results if available (e.g., DB id)
            job_id = job.get("id", "")
            if job_id and job_id in job_lookup:
                job = {**job_lookup[job_id], **job}

            applications.append({
                "job_id": job.get("id", ""),
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "status": "pending",
                "match_score": result.get("overall_score", 0),
                "recommendation_reason": result.get("recommendation_reason", ""),
                "next_follow_up": "3d",
            })

        kanban_state = {
            "pending": applications,
            "applied": [],
            "written_test": [],
            "round1": [],
            "round2": [],
            "hr_interview": [],
            "offer": [],
            "rejected": [],
        }

        return {
            "current_phase": "tracker",
            "applications": applications,
            "kanban_state": kanban_state,
        }


# Singleton instance
tracker_agent = TrackerAgent()
