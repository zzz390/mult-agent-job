"""Behavioral question generator using LLM (STAR format)."""

import json
from typing import Any

from langchain_openai import ChatOpenAI

from job_agent_os.prompts.loader import load_prompt
from job_agent_os.settings import get_settings


async def generate_behavior_questions(
    project_experience: str,
    job_title: str,
    count: int = 5,
) -> list[dict[str, Any]]:
    """Generate behavioral interview questions using LLM.

    Args:
        project_experience: User's project experience text
        job_title: Target job title
        count: Number of questions to generate

    Returns:
        List of question dicts in STAR format
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

    system_prompt, user_prompt = load_prompt("behavior_questions", {
        "project_experience": project_experience,
        "job_title": job_title,
        "count": count,
    })

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        return _parse_questions(response.content)
    except Exception:
        return _fallback_behavior_questions(count)


def _parse_questions(content: str) -> list[dict]:
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
                q.setdefault("type", "behavioral")
            return questions
        return []
    except (json.JSONDecodeError, IndexError):
        return []


def _fallback_behavior_questions(count: int) -> list[dict]:
    """Generate fallback behavioral questions without LLM."""
    templates = [
        ("请描述一次你在项目中遇到重大技术挑战的经历，你是如何解决的？", "问题解决"),
        ("请举例说明你如何在团队中推动一个有分歧的技术决策？", "团队协作"),
        ("请描述一次你在紧迫deadline下完成任务的经历？", "抗压能力"),
        ("请举例说明你如何主动发现并解决一个潜在问题？", "主动性"),
        ("请描述一次你向非技术人员解释复杂技术问题的经历？", "沟通能力"),
    ]
    questions = []
    for i in range(min(count, len(templates))):
        question, category = templates[i]
        questions.append({
            "id": i + 1,
            "type": "behavioral",
            "category": category,
            "difficulty": "medium",
            "question": question,
            "reference_answer": "使用STAR法则：描述情境(Situation)、任务(Task)、行动(Action)、结果(Result)",
            "scoring_criteria": ["情境清晰", "行动具体", "结果量化", "有反思总结"],
            "follow_up": None,
        })
    return questions
