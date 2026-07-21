"""Resume Agent - Optimize resume for target jobs using LLM."""

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState
from job_agent_os.tools.resume.keyword_optimizer import optimize_resume_keywords


class ResumeAgent(BaseAgent):
    """Resume Agent optimizes resume for target job descriptions.

    Uses LLM to optimize wording (constraint: never fabricate experience).
    Generates before/after/reason diff for each change.
    """

    name = "resume"
    required_tools = ["keyword_optimizer"]
    prompt_key = "optimize_resume"

    async def execute(self, state: JobAgentState) -> dict:
        """Optimize resume based on target JD."""
        match_results = state.get("match_results", [])
        user_profile = state.get("user_profile") or {}

        if not match_results:
            return {
                "current_phase": "resume",
                "optimized_resume": None,
                "resume_diff": [],
            }

        # Get top job as target
        top_job = match_results[0].get("job", {})
        job_description = self._build_job_description(top_job)
        resume_content = self._build_resume_text(user_profile)

        if not resume_content:
            return {
                "current_phase": "resume",
                "optimized_resume": {"original": user_profile, "optimized": user_profile, "target_job": top_job.get("title", "")},
                "resume_diff": [],
                "resume_approved": False,
            }

        # Call LLM optimization tool
        try:
            result = await optimize_resume_keywords(
                resume_content=resume_content,
                job_description=job_description,
            )
            optimized_resume = {
                "original": user_profile,
                "optimized_text": result.get("optimized_resume", resume_content),
                "target_job": top_job.get("title", ""),
                "suggestions": result.get("suggestions", []),
            }
            resume_diff = result.get("resume_diff", [])
        except Exception:
            optimized_resume = {
                "original": user_profile,
                "optimized": user_profile,
                "target_job": top_job.get("title", ""),
            }
            resume_diff = [{"section": "技能", "action": "reorder", "reason": "将匹配技能前置"}]

        return {
            "current_phase": "resume",
            "optimized_resume": optimized_resume,
            "resume_diff": resume_diff,
            "resume_approved": False,  # Requires human approval
        }

    def _build_job_description(self, job: dict) -> str:
        """Build a text description of the target job."""
        parts = [f"岗位: {job.get('title', '')}", f"公司: {job.get('company', '')}"]
        if job.get("skills_required"):
            parts.append(f"技能要求: {', '.join(job['skills_required'])}")
        if job.get("responsibilities"):
            parts.append(f"岗位职责: {'; '.join(job['responsibilities'][:3])}")
        return "\n".join(parts)

    def _build_resume_text(self, user_profile: dict) -> str:
        """Build resume text from user profile."""
        if not user_profile:
            return ""
        parts = []
        if user_profile.get("skills"):
            parts.append(f"技能: {', '.join(user_profile['skills'])}")
        if user_profile.get("education"):
            parts.append(f"学历: {user_profile['education']}")
        if user_profile.get("experience"):
            parts.append(f"经历: {user_profile['experience']}")
        if user_profile.get("projects"):
            parts.append(f"项目: {user_profile['projects']}")
        return "\n".join(parts) if parts else str(user_profile)


resume_agent = ResumeAgent()
