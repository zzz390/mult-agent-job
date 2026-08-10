"""Interview Agent - Generate interview questions (ReAct mode)."""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState

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
    """Interview Agent generates interview questions (ReAct)."""

    name = "interview"
    system_prompt = INTERVIEW_SYSTEM_PROMPT
    agent_tools = ["tech_question_gen", "behavior_question_gen"]
    max_iterations = 4

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build interview question generation task."""
        match_results = state.get("match_results", [])
        user_profile = state.get("user_profile") or {}
        task = self._get_task_instruction(state)

        # Get target job info
        top_job = match_results[0].get("job", {}) if match_results else {}
        job_title = top_job.get("title", "软件工程师")
        skills = top_job.get("skills_required", [])

        # Get user experiences for behavioral questions
        experiences = []
        if user_profile.get("projects"):
            experiences.extend(user_profile["projects"][:3] if isinstance(user_profile["projects"], list) else [str(user_profile["projects"])])
        if user_profile.get("internships"):
            experiences.extend(user_profile["internships"][:2] if isinstance(user_profile["internships"], list) else [str(user_profile["internships"])])

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

    def _parse_final_output(self, messages: list[BaseMessage], state: JobAgentState) -> dict:
        """Extract interview questions from tool outputs."""
        questions: list[dict] = []

        # Collect from tool messages
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            try:
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
                    if "[" in content:
                        json_str = content[content.index("["):content.rindex("]") + 1]
                        parsed = json.loads(json_str)
                        if isinstance(parsed, list):
                            questions = parsed
                except (json.JSONDecodeError, ValueError):
                    pass

        # Ensure IDs (create new dicts to avoid in-place mutation of originals)
        questions = [{**q, "id": i} if "id" not in q else q for i, q in enumerate(questions, 1)]

        return {
            "current_phase": "interview",
            "interview_questions": questions,
        }


# Singleton instance
interview_agent = InterviewAgent()
