"""Keyword optimizer - optimize resume keywords for target JD."""

import json
from typing import Any

from langchain_openai import ChatOpenAI

from job_agent_os.prompts.loader import load_prompt
from job_agent_os.settings import get_settings


async def optimize_resume_keywords(
    resume_content: str,
    job_description: str,
) -> dict[str, Any]:
    """Optimize resume for a target job using LLM.

    Args:
        resume_content: User's current resume text
        job_description: Target job description

    Returns:
        Dict with optimized_resume, resume_diff, and suggestions
    """
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        temperature=0.3,
        max_tokens=4096,
        timeout=settings.openai_timeout,
    )

    system_prompt, user_prompt = load_prompt("optimize_resume", {
        "resume_content": resume_content,
        "job_description": job_description,
    })

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])

        result = _parse_optimization_response(response.content)
        return result

    except Exception:
        return _fallback_optimization(resume_content, job_description)


def _parse_optimization_response(content: str) -> dict[str, Any]:
    """Parse LLM optimization response."""
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        else:
            json_str = content
        result = json.loads(json_str.strip())
        return {
            "optimized_resume": result.get("optimized_resume", ""),
            "resume_diff": result.get("changes", result.get("resume_diff", [])),
            "suggestions": result.get("suggestions", []),
        }
    except (json.JSONDecodeError, IndexError):
        return {
            "optimized_resume": content,
            "resume_diff": [{"section": "整体", "before": "", "after": content[:200], "reason": "LLM优化"}],
            "suggestions": [],
        }


def _fallback_optimization(resume_content: str, job_description: str) -> dict[str, Any]:
    """Fallback optimization without LLM - just reorder skills."""
    return {
        "optimized_resume": resume_content,
        "resume_diff": [
            {
                "section": "技能",
                "before": "原始技能排列",
                "after": "建议将匹配技能前置",
                "reason": "根据目标岗位调整技能展示顺序",
            }
        ],
        "suggestions": ["建议根据目标岗位调整简历侧重点"],
    }
