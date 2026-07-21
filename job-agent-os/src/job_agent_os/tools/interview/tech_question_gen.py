"""Technical question generator using LLM."""

import json
from typing import Any

from langchain_openai import ChatOpenAI

from job_agent_os.prompts.loader import load_prompt
from job_agent_os.settings import get_settings


async def generate_tech_questions(
    job_title: str,
    skills: list[str],
    difficulty: str = "mixed",
    count: int = 5,
) -> list[dict[str, Any]]:
    """Generate technical interview questions using LLM.

    Args:
        job_title: Target job title
        skills: Required technical skills
        difficulty: Difficulty level (easy/medium/hard/mixed)
        count: Number of questions to generate

    Returns:
        List of question dicts
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

    system_prompt, user_prompt = load_prompt("tech_questions", {
        "job_title": job_title,
        "skills": ", ".join(skills),
        "difficulty": difficulty,
        "count": count,
    })

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        return _parse_questions(response.content, "technical")
    except Exception:
        return _fallback_tech_questions(skills, count)


def _parse_questions(content: str, question_type: str) -> list[dict]:
    """Parse questions from LLM response."""
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        else:
            json_str = content
        questions = json.loads(json_str.strip())
        if isinstance(questions, list):
            for i, q in enumerate(questions, 1):
                q.setdefault("id", i)
                q.setdefault("type", question_type)
            return questions
        return []
    except (json.JSONDecodeError, IndexError):
        return []


def _fallback_tech_questions(skills: list[str], count: int) -> list[dict]:
    """Generate fallback questions without LLM."""
    questions = []
    templates = [
        ("请解释 {skill} 的核心原理和使用场景", "medium"),
        ("{skill} 中常见的性能优化方法有哪些？", "medium"),
        ("请设计一个使用 {skill} 的系统方案", "hard"),
    ]
    for i in range(min(count, len(skills) * len(templates))):
        skill = skills[i % len(skills)] if skills else "编程"
        template, diff = templates[i % len(templates)]
        questions.append({
            "id": i + 1,
            "type": "technical",
            "category": skill,
            "difficulty": diff,
            "question": template.format(skill=skill),
            "reference_answer": f"关于{skill}的详细解答...",
            "scoring_criteria": ["概念清晰", "原理正确", "有实践经验"],
            "follow_up": None,
        })
    return questions
