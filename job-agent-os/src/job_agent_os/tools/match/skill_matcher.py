"""Skill matcher - keyword-based skill matching (exact + fuzzy)."""


def match_skills(job_skills: list[str], user_skills: list[str]) -> dict:
    """Match job required skills against user skills.

    Args:
        job_skills: Skills required by the job
        user_skills: Skills the user has

    Returns:
        Dict with matched_skills, missing_skills, and match_ratio
    """
    if not job_skills:
        return {"matched_skills": [], "missing_skills": [], "match_ratio": 1.0}

    user_skills_lower = {s.lower().strip() for s in user_skills}
    matched = []
    missing = []

    for skill in job_skills:
        skill_lower = skill.lower().strip()
        if _is_skill_matched(skill_lower, user_skills_lower):
            matched.append(skill)
        else:
            missing.append(skill)

    match_ratio = len(matched) / len(job_skills) if job_skills else 1.0

    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "match_ratio": round(match_ratio, 3),
    }


def _is_skill_matched(skill: str, user_skills: set[str]) -> bool:
    """Check if a skill matches any user skill (exact + fuzzy)."""
    # Exact match
    if skill in user_skills:
        return True

    # Fuzzy: check if skill is substring of any user skill or vice versa
    for user_skill in user_skills:
        if skill in user_skill or user_skill in skill:
            return True

    # Common aliases
    aliases: dict[str, list[str]] = {
        "springboot": ["spring boot", "spring-boot", "spring"],
        "spring": ["springboot", "spring boot", "spring-boot"],
        "js": ["javascript"],
        "javascript": ["js"],
        "ts": ["typescript"],
        "typescript": ["ts"],
        "py": ["python"],
        "python": ["py"],
        "k8s": ["kubernetes"],
        "kubernetes": ["k8s"],
        "postgres": ["postgresql"],
        "postgresql": ["postgres"],
        "mysql": ["sql"],
        "vue": ["vuejs", "vue.js"],
        "react": ["reactjs", "react.js"],
    }

    skill_aliases = aliases.get(skill, [])
    for alias in skill_aliases:
        if alias in user_skills:
            return True

    return False


def compute_skill_score(job_skills: list[str], user_skills: list[str]) -> float:
    """Compute a 0-100 skill match score."""
    result = match_skills(job_skills, user_skills)
    return round(result["match_ratio"] * 100, 1)
