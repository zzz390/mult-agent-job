"""Judges (Rule/LLM/Human).

Judge implementations:
- RuleBasedJudge: deterministic rule checks
- LLMJudge: LLM-as-Judge evaluation
"""

import json
from typing import Any

from langchain_openai import ChatOpenAI

from job_agent_os.core.llm_usage import message_content_to_text
from job_agent_os.settings import get_settings


class BaseJudge:
    """Base judge interface."""

    name: str = "base"

    async def judge(
        self,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        ground_truth: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Judge an output.

        Returns:
            Dict with 'score' (0-1), 'reason', and 'passed' (bool)
        """
        raise NotImplementedError


class RuleBasedJudge(BaseJudge):
    """Rule-based judge using deterministic checks."""

    name = "rule_based"

    def __init__(self, rules: list[dict[str, Any]] | None = None) -> None:
        self.rules = rules or []

    async def judge(
        self,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        ground_truth: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply rules to judge output."""
        passed_rules = 0
        total_rules = len(self.rules)
        failures: list[str] = []

        if total_rules == 0:
            return {
                "score": 0.0,
                "passed": False,
                "reason": "No evaluation rules configured",
                "details": {"passed": 0, "total": 0},
            }

        for rule in self.rules:
            rule_type = rule.get("type", "")
            field = rule.get("field", "")
            expected = rule.get("expected")

            actual = output_data.get(field)

            if rule_type == "equals":
                if actual == expected:
                    passed_rules += 1
                else:
                    failures.append(f"{field}: expected '{expected}', got '{actual}'")
            elif rule_type == "contains":
                if expected and str(expected) in str(actual or ""):
                    passed_rules += 1
                else:
                    failures.append(f"{field}: expected to contain '{expected}'")
            elif rule_type == "not_empty":
                if actual:
                    passed_rules += 1
                else:
                    failures.append(f"{field}: expected non-empty")
            elif rule_type == "in_range":
                min_val = rule.get("min", 0)
                max_val = rule.get("max", 1)
                try:
                    numeric_actual = float(str(actual))
                    if float(str(min_val)) <= numeric_actual <= float(str(max_val)):
                        passed_rules += 1
                    else:
                        failures.append(f"{field}: {actual} not in [{min_val}, {max_val}]")
                except (TypeError, ValueError):
                    failures.append(f"{field}: cannot convert '{actual}' to number")

        score = passed_rules / total_rules

        return {
            "score": round(score, 4),
            "passed": len(failures) == 0,
            "reason": "; ".join(failures) if failures else "All rules passed",
            "details": {"passed": passed_rules, "total": total_rules},
        }


class LLMJudge(BaseJudge):
    """LLM-as-Judge evaluation."""

    name = "llm_judge"

    def __init__(self, criteria: str | None = None) -> None:
        self.criteria = criteria or (
            "请评估输出质量，考虑以下维度：\n"
            "1. 准确性：输出是否正确\n"
            "2. 完整性：是否覆盖所有要求\n"
            "3. 一致性：是否与输入逻辑一致\n"
            "评分 0-1，并给出理由。"
        )

    async def judge(
        self,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        ground_truth: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Use LLM to judge output quality."""
        settings = get_settings()
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            temperature=0.0,
            max_tokens=512,
            timeout=30,
        )

        prompt = f"""评估标准：
{self.criteria}

输入：
{json.dumps(input_data, ensure_ascii=False, default=str)[:1000]}

输出：
{json.dumps(output_data, ensure_ascii=False, default=str)[:1000]}

{f'参考答案：{json.dumps(ground_truth, ensure_ascii=False, default=str)[:500]}' if ground_truth else ''}

请以JSON格式输出评估结果：{{"score": 0.0-1.0, "reason": "评估理由"}}"""

        try:
            response = await llm.ainvoke([
                {"role": "system", "content": "你是一个严格的AI输出质量评估专家。"},
                {"role": "user", "content": prompt},
            ])

            result = self._parse_response(message_content_to_text(response.content))
            return result

        except Exception as e:
            return {
                "score": 0.0,
                "passed": False,
                "reason": f"LLM judge failed: {str(e)}",
            }

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse LLM judge response."""
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            else:
                json_str = content
            data = json.loads(json_str.strip())
            score = float(data.get("score", 0.0))
            return {
                "score": max(0.0, min(1.0, score)),
                "passed": score >= 0.6,
                "reason": data.get("reason", ""),
            }
        except (json.JSONDecodeError, IndexError, ValueError):
            return {
                "score": 0.5,
                "passed": False,
                "reason": f"Failed to parse judge response: {content[:200]}",
            }
