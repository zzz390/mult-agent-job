"""Tracker Agent - Manage application status and create records."""

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState


class TrackerAgent(BaseAgent):
    """Tracker Agent manages application lifecycle and status.

    Creates application records for matched jobs,
    initializes kanban state, and sets follow-up reminders.
    """

    name = "tracker"
    required_tools: list[str] = []
    prompt_key = ""

    async def execute(self, state: JobAgentState) -> dict:
        """Create application records and initialize kanban."""
        match_results = state.get("match_results", [])

        applications = []
        for result in match_results[:5]:  # Top 5 jobs
            job = result.get("job", {})
            applications.append({
                "job_id": job.get("id", ""),
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "status": "pending",
                "match_score": result.get("overall_score", 0),
                "recommendation_reason": result.get("recommendation_reason", ""),
                "next_follow_up": "3d",  # Follow up in 3 days
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


tracker_agent = TrackerAgent()
