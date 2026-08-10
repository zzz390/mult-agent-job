"""Match Agent - Score and rank jobs against user profile (ReAct mode)."""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState

MATCH_SYSTEM_PROMPT = """你是岗位匹配评分专家。你的任务是对候选岗位进行评分和排序。

你可以使用以下工具：
1. rule_filter - 按硬性条件（学历、地区）过滤岗位列表
2. skill_matcher - 将岗位技能要求与用户技能进行匹配，返回匹配/缺失列表

工作流程：
1. 先用 rule_filter 过滤不满足硬性条件的岗位
2. 对通过过滤的岗位，用 skill_matcher 进行技能匹配
3. 综合技能匹配度、学历匹配、地区匹配计算总分（满分100）
4. 为每个岗位生成推荐理由和风险因素
5. 按总分降序排列

评分权重：技能匹配50% + 学历匹配20% + 经验匹配20% + 地区匹配10%

最终输出：以JSON数组格式输出匹配结果，每项包含：
job(岗位信息), overall_score, skill_match, education_match, matched_skills, missing_skills, recommendation_reason, risk_factors"""


class MatchAgent(BaseAgent):
    """Match Agent scores and ranks jobs against user profile (ReAct)."""

    name = "match"
    system_prompt = MATCH_SYSTEM_PROMPT
    agent_tools = ["rule_filter", "skill_matcher"]
    max_iterations = 5

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build match task from parsed_jobs and user_profile."""
        parsed_jobs = state.get("parsed_jobs", [])
        user_profile = state.get("user_profile") or {}
        task = self._get_task_instruction(state)

        jobs_summary = json.dumps(parsed_jobs[:10], ensure_ascii=False, default=str)
        profile_summary = json.dumps(user_profile, ensure_ascii=False) if user_profile else "暂无用户简历信息"

        content = (
            f"请对以下 {len(parsed_jobs)} 个岗位进行匹配评分：\n\n"
            f"## 候选岗位：\n{jobs_summary}\n\n"
            f"## 用户画像：\n{profile_summary}"
        )
        if task:
            content += f"\n\nSupervisor 补充指令：{task}"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

    def _parse_final_output(self, messages: list[BaseMessage], state: JobAgentState) -> dict:
        """Extract match results from tool outputs and AI response."""
        match_results: list[dict] = []

        # Try to parse from AI final message (LLM generates comprehensive scoring)
        content = self._get_last_ai_content(messages)
        if content:
            try:
                if "[" in content:
                    json_str = content[content.index("["):content.rindex("]") + 1]
                    parsed = json.loads(json_str)
                    if isinstance(parsed, list):
                        match_results = parsed
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: build basic match results from parsed_jobs
        if not match_results:
            parsed_jobs = state.get("parsed_jobs", [])
            user_profile = state.get("user_profile") or {}
            user_skills = user_profile.get("skills", [])
            user_skills_lower = {us.lower() for us in user_skills}

            for job in parsed_jobs[:10]:
                job_skills = job.get("skills_required", [])
                matched = [s for s in job_skills if s.lower() in user_skills_lower]
                missing = [s for s in job_skills if s.lower() not in user_skills_lower]
                score = (len(matched) / len(job_skills) * 100) if job_skills else 70.0

                match_results.append({
                    "job": job,
                    "overall_score": round(score * 0.5 + 75 * 0.5, 1),
                    "skill_match": round(score, 1),
                    "education_match": 80.0,
                    "matched_skills": matched,
                    "missing_skills": missing,
                    "recommendation_reason": f"匹配技能: {', '.join(matched[:3])}" if matched else job.get("title", ""),
                    "risk_factors": [f"缺少: {', '.join(missing[:3])}"] if len(missing) > 2 else [],
                })

        # Sort by score
        match_results.sort(key=lambda x: x.get("overall_score", 0), reverse=True)

        return {
            "current_phase": "match",
            "match_results": match_results[:10],
        }


# Singleton instance
match_agent = MatchAgent()
