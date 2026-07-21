"""JD structurer - uses LLM to parse raw JD text into structured format."""

import json
from typing import Any

from langchain_openai import ChatOpenAI

from job_agent_os.prompts.loader import load_prompt
from job_agent_os.settings import get_settings


async def structure_jd(
    title: str,
    company: str,
    raw_description: str,
    source_platform: str = "",
    source_url: str = "",
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
    llm = ChatOpenAI(
        model=settings.openai_model,
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

        result = _parse_json_response(response.content)
        # Ensure required fields
        result.setdefault("title", title)
        result.setdefault("company", company)
        result.setdefault("source_url", source_url)
        result.setdefault("source_platform", source_platform)
        result.setdefault("parse_confidence", 0.7)
        return result

    except Exception:
        # Fallback: basic extraction without LLM
        return _fallback_structure(title, company, raw_description, source_platform, source_url)


def _parse_json_response(content: str) -> dict:
    """Extract JSON from LLM response."""
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        else:
            json_str = content
        return json.loads(json_str.strip())
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
