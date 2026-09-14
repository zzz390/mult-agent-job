"""Match Agent - deterministically score and rank jobs against a profile."""

import json
import re
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.core.privacy import redact_pii
from job_agent_os.graph.state import JobAgentState
from job_agent_os.tools.match.skill_matcher import match_skills

MATCH_SYSTEM_PROMPT = """你是岗位匹配评分专家。你的任务是对候选岗位进行评分和排序。

你可以使用以下工具：
1. rule_filter - 按硬性条件（学历、地区）过滤岗位列表
2. skill_matcher - 将岗位技能要求与用户技能进行匹配，返回匹配/缺失列表

工作流程：
1. 先用 rule_filter 过滤不满足硬性条件的岗位
2. 对通过过滤的岗位，用 skill_matcher 进行技能匹配
3. 综合技能匹配度、学历匹配、地区匹配计算总分（满分100）
4. 为每个岗位生成推荐理由和风险因素
5. 按总分降序排列

评分权重：技能匹配50% + 学历匹配20% + 经验匹配20% + 地区匹配10%

最终输出：以JSON数组格式输出匹配结果，每项包含：
job(岗位信息), overall_score, skill_match, education_match, matched_skills, missing_skills, recommendation_reason, risk_factors"""


class MatchAgent(BaseAgent):
    """Match Agent scores and ranks jobs with an explainable formula."""

    name = "match"
    system_prompt = MATCH_SYSTEM_PROMPT
    agent_tools: list[str] = []
    max_iterations = 5
    scoring_version = "deterministic-v1"

    _EDUCATION_LEVELS = {
        "大专": 1,
        "专科": 1,
        "本科": 2,
        "学士": 2,
        "硕士": 3,
        "研究生": 3,
        "博士": 4,
        "bachelor": 2,
        "master": 3,
        "phd": 4,
    }

    async def execute(self, state: JobAgentState) -> dict[str, Any]:
        """Score jobs deterministically; use LLMs only for generative stages."""
        return {
            "current_phase": "match",
            "match_results": self._score_jobs(state),
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
        }

    def _score_jobs(self, state: JobAgentState) -> list[dict[str, Any]]:
        jobs = [job for job in state.get("parsed_jobs", []) if isinstance(job, dict)]
        profile = state.get("user_profile") or {}
        user_skills = [str(skill) for skill in profile.get("skills", []) if skill]
        preferred_locations = [
            str(location).strip()
            for location in profile.get("preferred_locations", [])
            if str(location).strip()
        ]
        user_education = self._education_level(profile.get("education"))
        user_experience = self._number(profile.get("experience_years"))

        results: list[dict[str, Any]] = []
        for job in jobs[:10]:
            job_education_text = job.get("education") or job.get("education_required")
            job_education = self._education_level(job_education_text)
            job_location = str(job.get("location") or "")

            # Known hard constraints are deterministic filters. Unknown user
            # data is retained but lowers confidence instead of being invented.
            if job_education and user_education and user_education < job_education:
                continue
            if preferred_locations and job_location and not any(
                location.lower() in job_location.lower()
                for location in preferred_locations
            ):
                continue

            required_skills = [
                str(skill)
                for skill in job.get("skills_required", [])
                if str(skill).strip()
            ]
            skill_result = match_skills(required_skills, user_skills)
            skill_score = float(skill_result["match_ratio"]) * 100

            education_score, education_known = self._education_score(
                job_education, user_education
            )
            experience_score, experience_known = self._experience_score(
                job.get("experience") or job.get("experience_required"),
                user_experience,
            )
            location_score, location_known = self._location_score(
                job_location, preferred_locations
            )
            skill_known = not required_skills or bool(user_skills)

            breakdown = {
                "skill": round(skill_score, 1),
                "education": round(education_score, 1),
                "experience": round(experience_score, 1),
                "location": round(location_score, 1),
            }
            overall = (
                breakdown["skill"] * 0.5
                + breakdown["education"] * 0.2
                + breakdown["experience"] * 0.2
                + breakdown["location"] * 0.1
            )
            if not profile:
                overall = min(overall, 20.0)

            confidence = (
                (0.5 if skill_known else 0.0)
                + (0.2 if education_known else 0.0)
                + (0.2 if experience_known else 0.0)
                + (0.1 if location_known else 0.0)
            )
            risks = self._risk_factors(
                profile=profile,
                missing_skills=skill_result["missing_skills"],
                job_education=job_education,
                user_education=user_education,
                experience_known=experience_known,
            )
            matched = skill_result["matched_skills"]
            reason = (
                f"匹配技能：{', '.join(matched[:3])}"
                if matched
                else "未发现可验证的技能匹配证据"
            )

            results.append(
                {
                    "job": job,
                    "overall_score": round(overall, 1),
                    "skill_match": breakdown["skill"],
                    "education_match": breakdown["education"],
                    "experience_match": breakdown["experience"],
                    "location_match": breakdown["location"],
                    "matched_skills": matched,
                    "missing_skills": skill_result["missing_skills"],
                    "recommendation_reason": reason,
                    "risk_factors": risks,
                    "score_breakdown": breakdown,
                    "score_confidence": round(confidence, 2),
                    "scoring_version": self.scoring_version,
                }
            )

        results.sort(key=lambda item: item["overall_score"], reverse=True)
        return results

    @classmethod
    def _education_level(cls, value: object) -> int | None:
        if isinstance(value, dict):
            value = value.get("degree") or value.get("level")
        text = str(value or "").lower()
        return next(
            (level for name, level in cls._EDUCATION_LEVELS.items() if name in text),
            None,
        )

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, int | float):
            return float(value)
        match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
        return float(match.group()) if match else None

    @staticmethod
    def _education_score(
        required: int | None, actual: int | None
    ) -> tuple[float, bool]:
        if required is None:
            return 100.0, True
        if actual is None:
            return 0.0, False
        return (100.0 if actual >= required else 0.0), True

    @classmethod
    def _experience_score(
        cls, requirement: object, actual_years: float | None
    ) -> tuple[float, bool]:
        text = str(requirement or "").lower()
        if not text or any(marker in text for marker in ("不限", "无要求", "应届")):
            return 100.0, True
        required_years = cls._number(text)
        if required_years is None or actual_years is None:
            return 0.0, False
        if required_years <= 0:
            return 100.0, True
        return min(100.0, actual_years / required_years * 100), True

    @staticmethod
    def _location_score(
        job_location: str, preferred_locations: list[str]
    ) -> tuple[float, bool]:
        if not preferred_locations:
            return 100.0, True
        if not job_location:
            return 0.0, False
        matches = any(
            location.lower() in job_location.lower()
            for location in preferred_locations
        )
        return (100.0 if matches else 0.0), True

    @staticmethod
    def _risk_factors(
        *,
        profile: dict[str, Any],
        missing_skills: list[str],
        job_education: int | None,
        user_education: int | None,
        experience_known: bool,
    ) -> list[str]:
        risks: list[str] = []
        if missing_skills:
            risks.append(f"缺少技能：{', '.join(missing_skills[:3])}")
        if job_education is not None and user_education is None:
            risks.append("简历学历信息不足，无法验证学历要求")
        if not experience_known:
            risks.append("工作年限信息不足，无法验证经验要求")
        if not profile:
            risks.append("未提供用户简历，综合评分上限为20")
        return risks

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build match task from parsed_jobs and user_profile."""
        parsed_jobs = state.get("parsed_jobs", [])
        user_profile = redact_pii(state.get("user_profile") or {})
        task = self._get_task_instruction(state)

        jobs_summary = json.dumps(parsed_jobs[:10], ensure_ascii=False, default=str)
        profile_summary = json.dumps(user_profile, ensure_ascii=False) if user_profile else "暂无用户简历信息"

        content = (
            f"请对以下 {len(parsed_jobs)} 个岗位进行匹配评分：\n\n"
            f"## 候选岗位：\n{jobs_summary}\n\n"
            f"## 用户画像：\n{profile_summary}"
        )
        if task:
            content += f"\n\nSupervisor 补充指令：{task}"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

    def _parse_final_output(
        self, messages: list[BaseMessage], state: JobAgentState
    ) -> dict[str, Any]:
        """Compatibility hook for callers that still use the BaseAgent API."""
        return {
            "current_phase": "match",
            "match_results": self._score_jobs(state),
        }


# Singleton instance
match_agent = MatchAgent()
