"""Parse Agent - Parse job descriptions using LLM structuring."""

import asyncio

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState
from job_agent_os.tools.parse.html_parser import fetch_and_extract_html
from job_agent_os.tools.parse.jd_structurer import structure_jd


class ParseAgent(BaseAgent):
    """Parse Agent extracts structured information from job descriptions.

    Uses LLM to structure raw JD text into ParsedJD format.
    Batch concurrent parsing with asyncio.Semaphore.
    confidence < 0.6 marks as failed.
    """

    name = "parse"
    required_tools = ["html_parser", "jd_structurer"]
    prompt_key = "structure_jd"

    async def execute(self, state: JobAgentState) -> dict:
        """Parse search results into structured JDs."""
        search_results = state.get("search_results", [])

        if not search_results:
            return {
                "current_phase": "parse",
                "parsed_jobs": [],
                "parse_failures": [],
            }

        # Batch concurrent parsing with semaphore
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent
        tasks = [self._parse_single_job(job, semaphore) for job in search_results]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        parsed_jobs = []
        parse_failures = []

        for job, result in zip(search_results, results):
            if isinstance(result, Exception):
                parse_failures.append(job.get("source_url", "unknown"))
            elif result and result.get("parse_confidence", 0) >= 0.6:
                parsed_jobs.append(result)
            else:
                parse_failures.append(job.get("source_url", "unknown"))

        return {
            "current_phase": "parse",
            "parsed_jobs": parsed_jobs,
            "parse_failures": parse_failures,
        }

    async def _parse_single_job(self, job: dict, semaphore: asyncio.Semaphore) -> dict:
        """Parse a single job with concurrency control."""
        async with semaphore:
            # Try to fetch full description if URL available
            raw_description = job.get("raw_description", "")
            source_url = job.get("source_url", "")

            if not raw_description and source_url:
                raw_description = await fetch_and_extract_html(source_url)

            # Structure the JD using LLM
            structured = await structure_jd(
                title=job.get("title", ""),
                company=job.get("company", ""),
                raw_description=raw_description,
                source_platform=job.get("source_platform", ""),
                source_url=source_url,
            )

            return structured


parse_agent = ParseAgent()
