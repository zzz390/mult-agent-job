"""Search Agent - Search job platforms in parallel with real adapters."""

import asyncio

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState
from job_agent_os.tools.common.dedup import dedup_jobs
from job_agent_os.tools.search.base import PlatformAdapter
from job_agent_os.tools.search.boss import BossAdapter
from job_agent_os.tools.search.guopin import GuopinAdapter
from job_agent_os.tools.search.niuke import NiukeAdapter


class SearchAgent(BaseAgent):
    """Search Agent searches multiple job platforms in parallel.

    Uses real platform adapters (BOSS, Guopin, Niuke).
    Single platform failure does not block others (asyncio.gather + return_exceptions).
    Results are deduplicated by content_hash.
    """

    name = "search"
    required_tools = ["boss_search", "guopin_search", "niuke_search", "dedup"]
    prompt_key = ""

    def __init__(self) -> None:
        super().__init__()
        self.adapters: list[PlatformAdapter] = [
            BossAdapter(),
            GuopinAdapter(),
            NiukeAdapter(),
        ]

    async def execute(self, state: JobAgentState) -> dict:
        """Execute parallel search across platforms."""
        job_query = state.get("job_query", {})
        if not job_query:
            return {
                "current_phase": "search",
                "search_results": [],
                "search_errors": [{"error": "No job query provided"}],
                "platforms_searched": [],
            }

        # Search all platforms in parallel, single failure doesn't block
        tasks = [adapter.search(job_query) for adapter in self.adapters]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        all_jobs: list[dict] = []
        errors: list[dict] = []
        platforms_searched: list[str] = []

        for adapter, result in zip(self.adapters, results):
            if isinstance(result, Exception):
                errors.append({
                    "platform": adapter.platform_name,
                    "error": str(result),
                })
            else:
                all_jobs.extend(result)
                platforms_searched.append(adapter.platform_name)

        # Deduplicate by content hash
        unique_jobs = dedup_jobs(all_jobs)

        return {
            "current_phase": "search",
            "search_results": unique_jobs,
            "search_errors": errors,
            "platforms_searched": platforms_searched,
        }


# Singleton instance
search_agent = SearchAgent()
