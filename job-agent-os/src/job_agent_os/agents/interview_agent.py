"""Interview Agent - Generate interview questions using LLM tools."""

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState
from job_agent_os.tools.interview.behavior_question_gen import generate_behavior_questions
from job_agent_os.tools.interview.tech_question_gen import generate_tech_questions


class InterviewAgent(BaseAgent):
    """Interview Agent generates interview questions based on JD and resume.

    Generates both technical questions (from JD skills) and
    behavioral questions (from resume projects, STAR format).
    Each question includes reference answer and scoring criteria.
    """

    name = "interview"
    required_tools = ["tech_question_gen", "behavior_question_gen"]
    prompt_key = "tech_questions"

    async def execute(self, state: JobAgentState) -> dict:
        """Generate interview questions."""
        match_results = state.get("match_results", [])
        user_profile = state.get("user_profile") or {}

        if not match_results:
            return {"current_phase": "interview", "interview_questions": []}

        top_job = match_results[0].get("job", {})
        job_title = top_job.get("title", "软件工程师")
        skills = top_job.get("skills_required", [])

        questions: list[dict] = []

        # Generate technical questions
        try:
            tech_questions = await generate_tech_questions(
                job_title=job_title,
                skills=skills,
                difficulty="mixed",
                count=6,
            )
            questions.extend(tech_questions)
        except Exception:
            pass

        # Generate behavioral questions
        project_experience = user_profile.get("projects", user_profile.get("experience", ""))
        if isinstance(project_experience, list):
            project_experience = "\n".join(str(p) for p in project_experience)

        try:
            behavior_questions = await generate_behavior_questions(
                project_experience=str(project_experience) if project_experience else "应届生，有课程项目经验",
                job_title=job_title,
                count=4,
            )
            questions.extend(behavior_questions)
        except Exception:
            pass

        # Re-number questions
        for i, q in enumerate(questions, 1):
            q["id"] = i

        return {
            "current_phase": "interview",
            "interview_questions": questions[:10],
        }


interview_agent = InterviewAgent()
