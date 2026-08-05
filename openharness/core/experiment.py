from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel
from openharness.core.dataset import Dataset
from openharness.core.types import EvaluationResult, MetricScore
from openharness.core.harness import Harness


class ExperimentResult(BaseModel):
    experiment_name: str
    variant_a_name: str
    variant_b_name: str
    total_cases: int
    variant_a_pass_rate: float
    variant_b_pass_rate: float
    variant_a_avg_score: float
    variant_b_avg_score: float
    variant_a_avg_duration_ms: float
    variant_b_avg_duration_ms: float
    win_rate_b_over_a: float  # Percentage of cases where B outperformed A
    diff_details: List[Dict[str, Any]]


def run_ab_experiment(
    experiment_name: str,
    variant_a_name: str,
    agent_a_fn: Callable[[Any], Any],
    variant_b_name: str,
    agent_b_fn: Callable[[Any], Any],
    dataset: Dataset,
    evaluators: List[Callable[[Any], MetricScore]],
    db_path: str = ".openharness/evals.db"
) -> ExperimentResult:
    """Run an A/B benchmark experiment comparing Variant A vs Variant B across a dataset."""
    h_a = Harness(name=f"Exp: {experiment_name} ({variant_a_name})", db_path=db_path)
    h_b = Harness(name=f"Exp: {experiment_name} ({variant_b_name})", db_path=db_path)

    results_a: List[EvaluationResult] = []
    results_b: List[EvaluationResult] = []
    diff_details: List[Dict[str, Any]] = []

    b_wins = 0

    for case in dataset.cases:
        res_a = h_a.run_case(
            test_case_name=f"{case.name} [{variant_a_name}]",
            agent_fn=agent_a_fn,
            input_data=case.input,
            evaluators=evaluators
        )
        res_b = h_b.run_case(
            test_case_name=f"{case.name} [{variant_b_name}]",
            agent_fn=agent_b_fn,
            input_data=case.input,
            evaluators=evaluators
        )

        results_a.append(res_a)
        results_b.append(res_b)

        delta_score = res_b.total_score - res_a.total_score
        is_b_win = delta_score > 0 or (res_b.passed and not res_a.passed)
        if is_b_win:
            b_wins += 1

        diff_details.append({
            "test_case_name": case.name,
            "score_a": res_a.total_score,
            "score_b": res_b.total_score,
            "passed_a": res_a.passed,
            "passed_b": res_b.passed,
            "duration_ms_a": res_a.duration_ms,
            "duration_ms_b": res_b.duration_ms,
            "delta_score": round(delta_score, 4),
            "winner": variant_b_name if is_b_win else (variant_a_name if res_a.total_score > res_b.total_score else "TIE")
        })

    h_a.save()
    h_b.save()

    total = len(dataset.cases) or 1
    pass_a = sum(1 for r in results_a if r.passed) / total
    pass_b = sum(1 for r in results_b if r.passed) / total
    score_a = sum(r.total_score for r in results_a) / total
    score_b = sum(r.total_score for r in results_b) / total
    dur_a = sum(r.duration_ms for r in results_a) / total
    dur_b = sum(r.duration_ms for r in results_b) / total

    return ExperimentResult(
        experiment_name=experiment_name,
        variant_a_name=variant_a_name,
        variant_b_name=variant_b_name,
        total_cases=len(dataset.cases),
        variant_a_pass_rate=round(pass_a, 4),
        variant_b_pass_rate=round(pass_b, 4),
        variant_a_avg_score=round(score_a, 4),
        variant_b_avg_score=round(score_b, 4),
        variant_a_avg_duration_ms=round(dur_a, 2),
        variant_b_avg_duration_ms=round(dur_b, 2),
        win_rate_b_over_a=round(b_wins / total, 4),
        diff_details=diff_details
    )
