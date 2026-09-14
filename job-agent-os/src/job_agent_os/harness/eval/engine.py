"""Evaluation engine.

Provides EvalEngine for:
- Sample evaluation (single case)
- Batch evaluation (dataset)
- Regression evaluation (compare runs)
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from job_agent_os.harness.eval.judges import BaseJudge, RuleBasedJudge
from job_agent_os.harness.eval.metrics import MetricResult


@dataclass
class EvalCase:
    """A single evaluation case."""

    input_data: dict
    expected_output: dict | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    """Result of evaluating a single case."""

    case_index: int
    score: float
    passed: bool
    reason: str
    actual_output: dict | None = None
    duration_ms: int = 0


@dataclass
class EvalReport:
    """Aggregate evaluation report."""

    total_cases: int
    passed_cases: int
    failed_cases: int
    avg_score: float
    pass_rate: float
    results: list[EvalResult] = field(default_factory=list)
    metrics: list[MetricResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""


class EvalEngine:
    """Evaluation engine for agent outputs.

    Supports:
    - evaluate_single: Evaluate one case
    - evaluate_batch: Evaluate a dataset
    - compare_runs: Regression comparison
    """

    def __init__(self, judge: BaseJudge | None = None) -> None:
        self.judge = judge or RuleBasedJudge()

    async def evaluate_single(
        self,
        input_data: dict,
        actual_output: dict,
        expected_output: dict | None = None,
    ) -> EvalResult:
        """Evaluate a single case.

        Args:
            input_data: Input that was given to the agent
            actual_output: Agent's actual output
            expected_output: Expected output (ground truth)

        Returns:
            EvalResult with score and pass/fail
        """
        import time

        start = time.perf_counter()

        judge_result = await self.judge.judge(
            input_data=input_data,
            output_data=actual_output,
            ground_truth=expected_output,
        )

        duration_ms = int((time.perf_counter() - start) * 1000)

        return EvalResult(
            case_index=0,
            score=judge_result.get("score", 0.0),
            passed=judge_result.get("passed", False),
            reason=judge_result.get("reason", ""),
            actual_output=actual_output,
            duration_ms=duration_ms,
        )

    async def evaluate_batch(
        self,
        cases: list[EvalCase],
        run_fn: Any | None = None,
    ) -> EvalReport:
        """Evaluate a batch of cases.

        Args:
            cases: List of evaluation cases
            run_fn: Optional async function to run agent on each case input.
                    If None, cases must include actual_output in metadata.

        Returns:
            EvalReport with aggregate results
        """
        started_at = datetime.now(UTC).isoformat()
        results: list[EvalResult] = []

        for i, case in enumerate(cases):
            # Get actual output
            if run_fn:
                try:
                    actual_output = await run_fn(case.input_data)
                except Exception as e:
                    actual_output = {"error": str(e)}
            else:
                actual_output = case.metadata.get("actual_output", {})

            # Judge
            judge_result = await self.judge.judge(
                input_data=case.input_data,
                output_data=actual_output,
                ground_truth=case.expected_output,
            )

            results.append(
                EvalResult(
                    case_index=i,
                    score=judge_result.get("score", 0.0),
                    passed=judge_result.get("passed", False),
                    reason=judge_result.get("reason", ""),
                    actual_output=actual_output,
                )
            )

        finished_at = datetime.now(UTC).isoformat()

        # Compute aggregates
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        avg_score = sum(r.score for r in results) / total if total > 0 else 0.0

        return EvalReport(
            total_cases=total,
            passed_cases=passed,
            failed_cases=total - passed,
            avg_score=round(avg_score, 4),
            pass_rate=round(passed / total, 4) if total > 0 else 0.0,
            results=results,
            started_at=started_at,
            finished_at=finished_at,
        )

    def compare_runs(
        self, baseline: EvalReport, current: EvalReport
    ) -> dict:
        """Compare two evaluation runs for regression detection.

        Returns:
            Dict with regression info
        """
        score_diff = current.avg_score - baseline.avg_score
        pass_rate_diff = current.pass_rate - baseline.pass_rate

        # Find regressions (cases that passed before but fail now)
        regressions = []
        for base_r, curr_r in zip(baseline.results, current.results, strict=False):
            if base_r.passed and not curr_r.passed:
                regressions.append({
                    "case_index": curr_r.case_index,
                    "baseline_score": base_r.score,
                    "current_score": curr_r.score,
                    "reason": curr_r.reason,
                })

        return {
            "score_diff": round(score_diff, 4),
            "pass_rate_diff": round(pass_rate_diff, 4),
            "is_regression": score_diff < -0.05 or len(regressions) > 0,
            "regression_count": len(regressions),
            "regressions": regressions,
            "baseline_avg": baseline.avg_score,
            "current_avg": current.avg_score,
        }
