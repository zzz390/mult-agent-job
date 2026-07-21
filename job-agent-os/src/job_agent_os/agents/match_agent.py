"""Match Agent - Match jobs with user resume using rule filter + skill matcher + LLM scoring."""

import json

from job_agent_os.agents.base import BaseAgent
from job_agent_os.graph.state import JobAgentState
from job_agent_os.tools.match.rule_filter import batch_rule_filter
from job_agent_os.tools.match.skill_matcher import compute_skill_score, match_skills


class MatchAgent(BaseAgent):
    """Match Agent scores and ranks jobs based on user profile.

    Pipeline:
    1. Rule filter (hard constraints: education, location)
    2. Skill matching (exact + fuzzy keyword matching)
    3. LLM comprehensive scoring + recommendation reason generation
    """

    name = "match"
    required_tools = ["rule_filter", "skill_matcher"]
    prompt_key = "score_and_rank"

    async def execute(self, state: JobAgentState) -> dict:
        """Match parsed jobs with user profile."""
        parsed_jobs = state.get("parsed_jobs", [])
        user_profile = state.get("user_profile") or {}

        if not parsed_jobs:
            return {"current_phase": "match", "match_results": []}

        # Step 1: Rule filter (hard constraints)
        filtered_jobs = batch_rule_filter(parsed_jobs, user_profile)

        # Step 2: Skill matching + scoring
        user_skills = user_profile.get("skills", [])
        match_results = []

        for job in filtered_jobs:
            job_skills = job.get("skills_required", [])
            skill_result = match_skills(job_skills, user_skills)
            skill_score = compute_skill_score(job_skills, user_skills)

            # Compute composite score
            education_score = self._education_score(job, user_profile)
            location_score = self._location_score(job, user_profile)
            experience_score = 75.0  # Default, could be enhanced

            overall_score = (
                skill_score * 0.5
                + education_score * 0.2
                + experience_score * 0.2
                + location_score * 0.1
            )

            match_results.append({
                "job": job,
                "overall_score": round(overall_score, 1),
                "skill_match": skill_score,
                "education_match": education_score,
                "experience_match": experience_score,
                "location_match": location_score,
                "matched_skills": skill_result["matched_skills"],
                "missing_skills": skill_result["missing_skills"],
                "recommendation_reason": self._generate_reason(skill_result, job),
                "risk_factors": self._identify_risks(skill_result, job, user_profile),
            })

        # Step 3: Try LLM scoring for top candidates
        if match_results and user_profile:
            try:
                match_results = await self._llm_rerank(match_results[:5], user_profile)
            except Exception:
                pass  # Keep rule-based scores if LLM fails

        # Sort by score descending
        match_results.sort(key=lambda x: x["overall_score"], reverse=True)

        return {
            "current_phase": "match",
            "match_results": match_results[:10],
        }

    async def _llm_rerank(self, candidates: list[dict], user_profile: dict) -> list[dict]:
        """Use LLM to rerank top candidates and generate better reasons."""
        llm = self._get_llm()

        jobs_desc = "\n".join(
            f"{i+1}. {c['job'].get('title', '')} @ {c['job'].get('company', '')} "
            f"(技能: {', '.join(c['job'].get('skills_required', [])[:5])})"
            for i, c in enumerate(candidates)
        )

        prompt = f"""用户技能: {', '.join(user_profile.get('skills', []))}
用户学历: {user_profile.get('education', '未知')}

候选岗位:
{jobs_desc}

请为每个岗位生成一句推荐理由（中文，20字以内），以JSON数组格式输出：
[{{"index": 1, "reason": "推荐理由"}}]"""

        response = await llm.ainvoke([
            {"role": "system", "content": "你是求职匹配专家，为候选人生成精准的推荐理由。"},
            {"role": "user", "content": prompt},
        ])

        try:
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            else:
                json_str = content
            reasons = json.loads(json_str.strip())
            for item in reasons:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(candidates):
                    candidates[idx]["recommendation_reason"] = item.get("reason", "")
        except (json.JSONDecodeError, IndexError):
            pass

        return candidates

    def _education_score(self, job: dict, user_profile: dict) -> float:
        job_edu = (job.get("education") or "").lower()
        user_edu = (user_profile.get("education") or "").lower()
        levels = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}
        job_level = levels.get(job_edu, 0)
        user_level = levels.get(user_edu, 0)
        if job_level == 0 or user_level == 0:
            return 80.0
        if user_level >= job_level:
            return 100.0
        return max(0.0, 100.0 - (job_level - user_level) * 30)

    def _location_score(self, job: dict, user_profile: dict) -> float:
        preferred = user_profile.get("preferred_locations", [])
        job_location = job.get("location", "")
        if not preferred or not job_location:
            return 80.0
        if any(loc in job_location for loc in preferred):
            return 100.0
        return 50.0

    def _generate_reason(self, skill_result: dict, job: dict) -> str:
        matched = skill_result["matched_skills"]
        if matched:
            return f"匹配技能: {', '.join(matched[:3])}"
        return f"{job.get('title', '')} - {job.get('company', '')}"

    def _identify_risks(self, skill_result: dict, job: dict, user_profile: dict) -> list[str]:
        risks = []
        missing = skill_result["missing_skills"]
        if len(missing) > 2:
            risks.append(f"缺少关键技能: {', '.join(missing[:3])}")
        if skill_result["match_ratio"] < 0.5:
            risks.append("技能匹配度偏低")
        return risks


match_agent = MatchAgent()
