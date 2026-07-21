"""Rule-based filter for hard constraints (education, location)."""


def rule_filter(job: dict, user_profile: dict) -> tuple[bool, str]:
    """Apply hard constraint filters.

    Args:
        job: Structured job dict
        user_profile: User profile dict

    Returns:
        Tuple of (passes_filter, reason_if_failed)
    """
    # Education filter
    job_education = (job.get("education") or "").lower()
    user_education = (user_profile.get("education") or "").lower()

    education_levels = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4, "bachelor": 2, "master": 3, "phd": 4}

    if job_education and user_education:
        job_level = education_levels.get(job_education, 0)
        user_level = education_levels.get(user_education, 0)
        if job_level > 0 and user_level > 0 and user_level < job_level:
            return False, f"学历要求不满足: 需要{job_education}, 当前{user_education}"

    # Location filter (if user has strict location preference)
    user_preferred_locations = user_profile.get("preferred_locations", [])
    job_location = job.get("location", "")
    if user_preferred_locations and job_location:
        location_match = any(loc in job_location for loc in user_preferred_locations)
        if not location_match:
            return False, f"工作地点不匹配: 岗位在{job_location}"

    return True, ""


def batch_rule_filter(jobs: list[dict], user_profile: dict) -> list[dict]:
    """Filter a batch of jobs, returning only those that pass hard constraints."""
    passed = []
    for job in jobs:
        passes, _ = rule_filter(job, user_profile)
        if passes:
            passed.append(job)
    return passed
