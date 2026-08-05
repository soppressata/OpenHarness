import time
import math
from typing import Any, Callable, Dict, List
from pydantic import BaseModel
from openharness.core.types import EvaluationResult, MetricScore
from openharness.core.harness import Harness


class SweepSummary(BaseModel):
    test_case_name: str
    n_runs: int
    passed_runs: int
    failed_runs: int
    pass_rate: float
    flakiness_score: float  # 0.0 = completely stable (100% pass or 0% pass), 1.0 = highly volatile
    avg_duration_ms: float
    std_duration_ms: float
    avg_score: float
    unique_tool_sequences: List[List[str]]
    results: List[EvaluationResult]


def run_determinism_sweep(
    test_case_name: str,
    agent_fn: Callable[[Any], Any],
    input_data: Any,
    evaluators: List[Callable[[Any], MetricScore]],
    n_runs: int = 5,
    db_path: str = ".openharness/evals.db"
) -> SweepSummary:
    """
    Run an agent N times over the exact same input to evaluate pass rate stability, 
    flakiness score, and variance in tool call execution paths.
    """
    h = Harness(name=f"Determinism Sweep: {test_case_name}", db_path=db_path)
    results: List[EvaluationResult] = []
    tool_sequences: List[List[str]] = []
    durations: List[float] = []
    scores: List[float] = []

    for i in range(n_runs):
        res = h.run_case(
            test_case_name=f"{test_case_name} (Run #{i+1})",
            agent_fn=agent_fn,
            input_data=input_data,
            evaluators=evaluators
        )
        results.append(res)
        durations.append(res.duration_ms)
        scores.append(res.total_score)

        if res.trajectory:
            tool_sequences.append(res.trajectory.get_tool_names())

    h.save()

    passed_count = sum(1 for r in results if r.passed)
    failed_count = n_runs - passed_count
    pass_rate = passed_count / n_runs

    # Flakiness metric calculation: p * (1 - p) * 4 -> 0.0 when p is 1.0 or 0.0, 1.0 when p is 0.5
    flakiness = round(pass_rate * (1.0 - pass_rate) * 4.0, 4)

    avg_duration = sum(durations) / n_runs
    variance_duration = sum((x - avg_duration) ** 2 for x in durations) / n_runs
    std_duration = math.sqrt(variance_duration)

    avg_score = sum(scores) / n_runs

    # Deduplicate unique tool sequences
    unique_seqs = []
    for seq in tool_sequences:
        if seq not in unique_seqs:
            unique_seqs.append(seq)

    return SweepSummary(
        test_case_name=test_case_name,
        n_runs=n_runs,
        passed_runs=passed_count,
        failed_runs=failed_count,
        pass_rate=round(pass_rate, 4),
        flakiness_score=flakiness,
        avg_duration_ms=round(avg_duration, 2),
        std_duration_ms=round(std_duration, 2),
        avg_score=round(avg_score, 4),
        unique_tool_sequences=unique_seqs,
        results=results
    )
