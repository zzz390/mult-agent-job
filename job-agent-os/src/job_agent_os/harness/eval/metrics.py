"""Evaluation metrics definition.

Metrics:
- Accuracy: correct / total
- Coverage: retrieved / relevant
- Consistency: repeated runs agreement
"""

from dataclasses import dataclass


@dataclass
class MetricResult:
    """Result of a metric evaluation."""

    name: str
    score: float
    details: dict | None = None


def accuracy(predictions: list, ground_truths: list) -> MetricResult:
    """Compute accuracy: exact match ratio.

    Args:
        predictions: List of predicted values
        ground_truths: List of ground truth values

    Returns:
        MetricResult with score 0-1
    """
    if not predictions or not ground_truths:
        return MetricResult(name="accuracy", score=0.0)

    correct = sum(1 for p, g in zip(predictions, ground_truths) if p == g)
    total = min(len(predictions), len(ground_truths))
    score = correct / total if total > 0 else 0.0

    return MetricResult(
        name="accuracy",
        score=round(score, 4),
        details={"correct": correct, "total": total},
    )


def coverage(retrieved: list, relevant: list) -> MetricResult:
    """Compute coverage (recall): how many relevant items were retrieved.

    Args:
        retrieved: List of retrieved items
        relevant: List of relevant (ground truth) items

    Returns:
        MetricResult with score 0-1
    """
    if not relevant:
        return MetricResult(name="coverage", score=1.0)

    retrieved_set = set(str(r) for r in retrieved)
    relevant_set = set(str(r) for r in relevant)
    hits = len(retrieved_set & relevant_set)
    score = hits / len(relevant_set) if relevant_set else 0.0

    return MetricResult(
        name="coverage",
        score=round(score, 4),
        details={"hits": hits, "relevant_total": len(relevant_set)},
    )


def consistency(results: list[list]) -> MetricResult:
    """Compute consistency: agreement across repeated runs.

    Args:
        results: List of result lists from repeated runs

    Returns:
        MetricResult with score 0-1 (1 = perfectly consistent)
    """
    if len(results) <= 1:
        return MetricResult(name="consistency", score=1.0)

    # Compare each run to the first run
    baseline = results[0]
    agreements = 0
    comparisons = 0

    for run in results[1:]:
        for b, r in zip(baseline, run):
            comparisons += 1
            if b == r:
                agreements += 1

    score = agreements / comparisons if comparisons > 0 else 0.0

    return MetricResult(
        name="consistency",
        score=round(score, 4),
        details={"agreements": agreements, "comparisons": comparisons, "runs": len(results)},
    )


def f1_score(precision: float, recall: float) -> MetricResult:
    """Compute F1 score from precision and recall."""
    if precision + recall == 0:
        score = 0.0
    else:
        score = 2 * precision * recall / (precision + recall)

    return MetricResult(
        name="f1_score",
        score=round(score, 4),
        details={"precision": precision, "recall": recall},
    )
