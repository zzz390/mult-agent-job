"""Interview Agent - generate interview questions concurrently.

Issue #2 (agent consolidation): after generating interview questions this
agent also creates application records + kanban state (formerly the
separate `tracker` agent), removing one Supervisor round trip.
"""

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.core.json_utils import extract_json_array
from job_agent_os.core.llm_usage import empty_token_usage, merge_token_usage
from job_agent_os.core.privacy import redact_pii
from job_agent_os.graph.selectors import selected_recommendations
from job_agent_os.graph.state import JobAgentState
from job_agent_os.settings import get_settings
from job_agent_os.tools.interview.behavior_question_gen import (
    generate_behavior_questions,
)
from job_agent_os.tools.interview.tech_question_gen import generate_tech_questions

logger = logging.getLogger(__name__)

INTERVIEW_SYSTEM_PROMPT = """你是面试题生成专家。你的任务是根据目标岗位生成面试题。

你可以使用以下工具：
1. tech_question_gen - 生成技术面试题（含参考答案和评分标准）
2. behavior_question_gen - 生成行为面试题（STAR格式）

工作策略：
1. 从目标岗位提取技术栈，调用 tech_question_gen 生成技术题
2. 从用户经历中提取项目经验，调用 behavior_question_gen 生成行为题
3. 技术题和行为题各生成 3-5 道

最终输出：以JSON数组格式输出所有面试题，每题包含：
id, type(technical/behavioral), category, difficulty, question, reference_answer, scoring_criteria"""


class InterviewAgent(BaseAgent):
    """Interview Agent generates questions and initializes application tracking.

    Also creates application records and kanban state (formerly the
    separate tracker agent, issue #2).
    """

    name = "interview"
    system_prompt = INTERVIEW_SYSTEM_PROMPT
    agent_tools: list[str] = []
    max_iterations = 4

    # How many top matches get application records (same as old tracker)
    max_applications = 5

    async def execute(self, state: JobAgentState) -> dict[str, Any]:
        """Generate independent question sets concurrently, then initialize tracking."""
        recommendations = selected_recommendations(state)
        top_job = recommendations[0].get("job", {}) if recommendations else {}
        profile = redact_pii(state.get("user_profile") or {})
        job_title = str(top_job.get("title") or "软件工程师")
        skills = [
            str(skill) for skill in top_job.get("skills_required", []) if skill
        ]
        experiences = self._experiences(profile)
        technical_usage = empty_token_usage()
        behavioral_usage = empty_token_usage()

        try:
            async with asyncio.timeout(get_settings().harness_tool_timeout_seconds):
                technical, behavioral = await asyncio.gather(
                    generate_tech_questions(
                        job_title=job_title,
                        skills=skills,
                        difficulty="mixed",
                        count=5,
                        use_fallback=bool(state.get("use_fallback_model")),
                        usage_sink=technical_usage,
                    ),
                    generate_behavior_questions(
                        project_experience=json.dumps(
                            experiences, ensure_ascii=False, default=str
                        ),
                        job_title=job_title,
                        count=3,
                        use_fallback=bool(state.get("use_fallback_model")),
                        usage_sink=behavioral_usage,
                    ),
                )
        except TimeoutError:
            technical, behavioral = [], []

        questions = [
            {**question, "id": index}
            for index, question in enumerate([*technical, *behavioral], 1)
            if isinstance(question, dict)
        ]
        result: dict[str, Any] = {
            "current_phase": "interview",
            "interview_questions": questions,
            "token_usage": merge_token_usage(technical_usage, behavioral_usage),
        }

        # Embedded tracker responsibility (issue #2)
        if not state.get("applications"):
            try:
                applications = self._create_applications(state)
                if applications:
                    result["applications"] = applications
                    result["kanban_state"] = self._build_kanban_state(applications)
                    # Traceability: record that tracker work happened
                    result.setdefault("agent_execution_order", []).append("tracker")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[interview] Inline application creation failed: {e}")

        return result

    @staticmethod
    def _experiences(profile: dict[str, Any]) -> list[object]:
        experiences: list[object] = []
        projects = profile.get("projects")
        internships = profile.get("internships")
        if projects:
            experiences.extend(projects[:3] if isinstance(projects, list) else [projects])
        if internships:
            experiences.extend(
                internships[:2] if isinstance(internships, list) else [internships]
            )
        return experiences

    def _create_applications(self, state: JobAgentState) -> list[dict[str, Any]]:
        """Build application records for the top matched jobs (tracker logic)."""
        match_results = selected_recommendations(state)
        applications: list[dict[str, Any]] = []
        for result in match_results[: self.max_applications]:
            job = result.get("job", {})
            applications.append({
                "job_id": job.get("id", ""),
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "status": "pending",
                "match_score": result.get("overall_score", 0),
                "recommendation_reason": result.get("recommendation_reason", ""),
                "next_follow_up": "3d",
            })
        return applications

    @staticmethod
    def _build_kanban_state(
        applications: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Initialize kanban with all applications in the pending column."""
        return {
            "pending": applications,
            "applied": [],
            "written_test": [],
            "round1": [],
            "round2": [],
            "hr_interview": [],
            "offer": [],
            "rejected": [],
        }

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build interview question generation task."""
        match_results = selected_recommendations(state)
        user_profile = redact_pii(state.get("user_profile") or {})
        task = self._get_task_instruction(state)

        # Get target job info
        top_job = match_results[0].get("job", {}) if match_results else {}
        job_title = top_job.get("title", "软件工程师")
        skills = top_job.get("skills_required", [])

        # Get user experiences for behavioral questions
        experiences = self._experiences(user_profile)

        content = (
            f"请为以下目标岗位生成面试题：\n\n"
            f"目标岗位: {job_title}\n"
            f"技术栈: {', '.join(skills) if skills else '通用'}\n"
            f"用户经历: {json.dumps(experiences, ensure_ascii=False) if experiences else '暂无'}\n\n"
            f"请生成 5 道技术题 + 3 道行为题。"
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
        """Extract interview questions from tool outputs."""
        questions: list[dict[str, Any]] = []

        # Collect from tool messages
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            try:
                if not isinstance(msg.content, str):
                    continue
                data = json.loads(msg.content)
                if isinstance(data, list):
                    questions.extend(data)
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: parse from AI response
        if not questions:
            content = self._get_last_ai_content(messages)
            if content:
                try:
                    parsed = extract_json_array(content)
                    if isinstance(parsed, list):
                        questions = parsed
                except ValueError:
                    pass

        # Ensure IDs (create new dicts to avoid in-place mutation of originals)
        questions = [{**q, "id": i} if "id" not in q else q for i, q in enumerate(questions, 1)]

        return {
            "current_phase": "interview",
            "interview_questions": questions,
        }


# Singleton instance
interview_agent = InterviewAgent()
