"""JD structurer - uses LLM to parse raw JD text into structured format."""

import asyncio
import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI

from job_agent_os.core.llm_usage import collect_message_usage, message_content_to_text
from job_agent_os.harness.recovery_manager import is_fallback_model_requested
from job_agent_os.prompts.loader import load_prompt
from job_agent_os.settings import get_settings

logger = logging.getLogger(__name__)

# Default concurrency for parallel JD structuring. Keeps LLM rate-limit
# pressure low while cutting N serial calls down to ~N/5 round trips.
DEFAULT_PARSE_CONCURRENCY = 5


async def structure_jd(
    title: str,
    company: str,
    raw_description: str,
    source_platform: str = "",
    source_url: str = "",
    use_fallback: bool = False,
    usage_sink: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    """Structure a raw JD using LLM.

    Args:
        title: Job title
        company: Company name
        raw_description: Raw JD text
        source_platform: Source platform name
        source_url: Source URL

    Returns:
        Structured JD dict with parse_confidence
    """
    settings = get_settings()
    use_fallback = use_fallback or is_fallback_model_requested()
    llm = ChatOpenAI(
        model=settings.openai_model_fallback if use_fallback else settings.openai_model,
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        temperature=0.1,
        max_tokens=2048,
        timeout=settings.openai_timeout,
    )

    system_prompt, user_prompt = load_prompt("structure_jd", {
        "title": title,
        "company": company,
        "raw_description": raw_description,
        "source_platform": source_platform,
        "source_url": source_url,
    })

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        if usage_sink is not None:
            collect_message_usage(response, usage_sink)

        result = _parse_json_response(message_content_to_text(response.content))
        if not result:
            return _fallback_structure(
                title, company, raw_description, source_platform, source_url
            )
        # Ensure required fields
        result.setdefault("title", title)
        result.setdefault("company", company)
        result.setdefault("source_url", source_url)
        result.setdefault("source_platform", source_platform)
        # A syntactically valid LLM structure with the required identity fields
        # is usable even when the model omitted its optional self-confidence.
        # Keep it above the batch acceptance threshold; heuristic fallback
        # results remain explicitly low-confidence (0.4).
        result.setdefault("parse_confidence", 0.8)
        return result

    except Exception:
        # Fallback: basic extraction without LLM
        return _fallback_structure(title, company, raw_description, source_platform, source_url)


def _parse_json_response(content: str) -> dict[str, Any]:
    """Extract JSON from LLM response."""
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        else:
            json_str = content
        decoded = json.loads(json_str.strip())
        return decoded if isinstance(decoded, dict) else {}
    except (json.JSONDecodeError, IndexError):
        return {}


def _fallback_structure(
    title: str, company: str, raw_description: str, source_platform: str, source_url: str
) -> dict[str, Any]:
    """Fallback structuring without LLM."""
    # Simple keyword-based skill extraction
    common_skills = [
        "Java", "Python", "Go", "C++", "JavaScript", "TypeScript",
        "Spring", "SpringBoot", "Django", "Flask", "FastAPI",
        "MySQL", "PostgreSQL", "Redis", "MongoDB",
        "Docker", "Kubernetes", "Linux",
        "React", "Vue", "Angular",
        "机器学习", "深度学习", "NLP", "CV",
    ]

    found_skills = [s for s in common_skills if s.lower() in raw_description.lower()]

    return {
        "title": title,
        "company": company,
        "location": None,
        "salary": None,
        "requirements": [],
        "skills_required": found_skills,
        "skills_preferred": [],
        "education": None,
        "experience": None,
        "responsibilities": [],
        "deadline": None,
        "source_url": source_url,
        "source_platform": source_platform,
        "parse_confidence": 0.4,
    }


async def structure_jds_parallel(
    raw_jobs: list[dict[str, Any]],
    max_concurrency: int = DEFAULT_PARSE_CONCURRENCY,
    min_confidence: float = 0.6,
    use_fallback: bool = False,
    usage_sink: dict[str, int | float] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Structure a batch of raw jobs concurrently (issue #9).

    Previously N jobs meant N serial LLM round trips (30-60s for 20 jobs).
    This fans the calls out with a semaphore to bound concurrency.

    Args:
        raw_jobs: Raw job dicts (need title/company, optionally raw_description)
        max_concurrency: Max parallel LLM calls (avoids rate limits)
        min_confidence: Threshold below which a job is reported as a failure

    Returns:
        (parsed_jobs, parse_failures) — structured JDs and failed source ids
    """
    if not raw_jobs:
        return [], []

    semaphore = asyncio.Semaphore(max_concurrency)

    async def parse_one(job: dict[str, Any]) -> dict[str, Any] | None:
        async with semaphore:
            try:
                parsed = await structure_jd(
                    title=job.get("title", ""),
                    company=job.get("company", ""),
                    raw_description=job.get("raw_description", "") or "",
                    source_platform=job.get("source_platform", ""),
                    source_url=job.get("source_url", ""),
                    use_fallback=use_fallback,
                    usage_sink=usage_sink,
                )
                for key in ("id", "content_hash"):
                    if job.get(key):
                        parsed[key] = job[key]
                return parsed
            except Exception as e:  # noqa: BLE001
                logger.warning("Parse failed for %s: %s", job.get("title"), e)
                return None

    results = await asyncio.gather(*(parse_one(j) for j in raw_jobs))

    parsed_jobs: list[dict[str, Any]] = []
    parse_failures: list[str] = []
    for job, parsed in zip(raw_jobs, results, strict=True):
        if parsed and parsed.get("title") and parsed.get("parse_confidence", 0) >= min_confidence:
            parsed_jobs.append(parsed)
        else:
            # Keep a basic passthrough entry so downstream match still sees the job
            parsed_jobs.append({
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location"),
                "salary": job.get("salary"),
                "skills_required": job.get("skills_required", []),
                "education": job.get("education"),
                "source_url": job.get("source_url", ""),
                "source_platform": job.get("source_platform", ""),
                "parse_confidence": 0.3,
                "parse_note": "fallback_unparsed",
            })
            parse_failures.append(job.get("source_url") or job.get("title") or "unknown")

    return parsed_jobs, parse_failures
