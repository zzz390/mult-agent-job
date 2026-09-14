"""Resume Agent - optimize a resume with one structured generation call."""

import asyncio
import json
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.core.json_utils import extract_json_object
from job_agent_os.core.llm_usage import empty_token_usage
from job_agent_os.core.privacy import redact_pii
from job_agent_os.graph.selectors import selected_recommendations
from job_agent_os.graph.state import JobAgentState
from job_agent_os.settings import get_settings
from job_agent_os.tools.resume.keyword_optimizer import optimize_resume_keywords

RESUME_SYSTEM_PROMPT = """你是简历优化专家。你的任务是针对目标岗位优化用户简历。

你可以使用以下工具：
1. keyword_optimizer - 使用LLM针对目标岗位优化简历关键词和措辞，返回修改对比

工作原则：
- 不捏造经历，只优化措辞和关键词
- 突出与目标岗位匹配的技能
- 量化成果（如"提升性能30%"）
- 生成修改对比（before/after/reason）

最终输出：以JSON格式输出，包含：
- optimized_resume: 优化后的简历文本
- resume_diff: 修改对比列表 [{section, before, after, reason}]"""


class ResumeAgent(BaseAgent):
    """Resume Agent optimizes a resume for the reviewed target job."""

    name = "resume"
    system_prompt = RESUME_SYSTEM_PROMPT
    agent_tools: list[str] = []
    max_iterations = 3

    async def execute(self, state: JobAgentState) -> dict[str, Any]:
        """Run the single required optimization directly, avoiding nested LLMs."""
        profile = redact_pii(state.get("user_profile") or {})
        recommendations = selected_recommendations(state)
        target_job = recommendations[0].get("job", {}) if recommendations else {}
        if not profile or not target_job:
            return {
                "current_phase": "resume",
                "optimized_resume": None,
                "resume_diff": [],
                "error_state": {
                    "error_type": "MissingResumeTarget",
                    "error_message": "简历或已确认的目标岗位为空",
                    "retry_count": 0,
                },
                "token_usage": self._zero_usage(),
            }

        job_description = json.dumps(target_job, ensure_ascii=False, default=str)
        instruction = self._get_task_instruction(state)
        if instruction:
            job_description += f"\nSupervisor 补充要求：{instruction}"

        resume_content = json.dumps(profile, ensure_ascii=False, default=str)
        usage = empty_token_usage()
        try:
            async with asyncio.timeout(get_settings().harness_tool_timeout_seconds):
                optimized = await optimize_resume_keywords(
                    resume_content=resume_content,
                    job_description=job_description,
                    use_fallback=bool(state.get("use_fallback_model")),
                    usage_sink=usage,
                )
        except TimeoutError:
            optimized = {
                "optimized_resume": resume_content,
                "resume_diff": [],
                "suggestions": ["简历优化超时，已保留原始内容，请稍后重试"],
            }

        return {
            "current_phase": "resume",
            "optimized_resume": optimized.get("optimized_resume") or resume_content,
            "resume_diff": optimized.get("resume_diff") or [],
            "resume_suggestions": optimized.get("suggestions") or [],
            "token_usage": usage,
        }

    @staticmethod
    def _zero_usage() -> dict[str, int | float]:
        return empty_token_usage()

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build resume optimization task."""
        user_profile = redact_pii(state.get("user_profile") or {})
        match_results = selected_recommendations(state)
        task = self._get_task_instruction(state)

        # Get target job description from top match
        target_job = match_results[0].get("job", {}) if match_results else {}
        job_desc = json.dumps(target_job, ensure_ascii=False, default=str)

        # Build resume content from user profile
        resume_content = json.dumps(user_profile, ensure_ascii=False) if user_profile else "暂无简历数据"

        content = (
            f"请针对以下目标岗位优化用户简历：\n\n"
            f"## 目标岗位：\n{job_desc}\n\n"
            f"## 用户简历：\n{resume_content}"
        )
        if task:
            content += f"\n\nSupervisor 补充指令：{task}"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

    def _parse_final_output(
        self, messages: list[BaseMessage], state: JobAgentState
    ) -> dict[str, Any]:
        """Extract resume optimization results."""
        optimized_resume = None
        resume_diff: list[dict[str, Any]] = []

        # Check tool outputs
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            try:
                if not isinstance(msg.content, str):
                    continue
                data = json.loads(msg.content)
                if isinstance(data, dict):
                    if data.get("optimized_resume"):
                        optimized_resume = data["optimized_resume"]
                    if data.get("resume_diff"):
                        resume_diff = data["resume_diff"]
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: parse from AI response
        if not optimized_resume:
            content = self._get_last_ai_content(messages)
            if content:
                try:
                    data = extract_json_object(content)
                    optimized_resume = data.get("optimized_resume", content)
                    resume_diff = data.get("resume_diff", [])
                except ValueError:
                    optimized_resume = content

        if not resume_diff:
            resume_diff = [{"section": "整体", "before": "", "after": "已优化关键词匹配", "reason": "针对目标岗位调整"}]

        return {
            "current_phase": "resume",
            "optimized_resume": optimized_resume if optimized_resume else None,
            "resume_diff": resume_diff,
        }


# Singleton instance
resume_agent = ResumeAgent()
