"""Tests that prevent vacuous evaluation success."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from job_agent_os.harness.eval.judges import RuleBasedJudge
from job_agent_os.services.evaluation_service import EvaluationService


async def test_rule_judge_without_rules_fails_closed() -> None:
    result = await RuleBasedJudge().judge({}, {})

    assert result["passed"] is False
    assert result["score"] == 0.0
    assert result["reason"] == "No evaluation rules configured"


async def test_evaluation_report_uses_labeled_count_column() -> None:
    query_result = MagicMock()
    query_result.all.return_value = [
        SimpleNamespace(
            agent_name="match",
            metric_name="accuracy",
            avg_score=0.75,
            evaluation_count=4,
        )
    ]
    db = AsyncMock()
    db.execute.return_value = query_result

    report = await EvaluationService(db).get_report(SimpleNamespace())

    assert report["summary"] == {
        "total_evaluations": 4,
        "overall_avg_score": 0.75,
    }
