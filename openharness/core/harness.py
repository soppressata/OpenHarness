"""
Harness module for OpenHarness.
Provides core functionality for the harness subsystem.
"""
import asyncio
import functools
import inspect
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Union
from openharness.core.types import EvaluationResult, MetricScore, TestCase, Trajectory
from openharness.core.storage import StorageEngine


class Harness:
    """Core OpenHarness Evaluator Runner."""

    def __init__(self, name: str = "OpenHarness Evaluation Run", db_path: str = ".openharness/evals.db"):
        self.name = name
        self.run_id = str(uuid.uuid4())[:8]
        self.storage = StorageEngine(db_path=db_path)
        self.results: List[EvaluationResult] = []

    def _execute_agent(self, agent_fn: Callable[[Any], Any], input_data: Any) -> tuple[Optional[Trajectory], Optional[str], Optional[str]]:
        trajectory: Optional[Trajectory] = None
        output = None
        error_msg = None

        try:
            raw_result = agent_fn(input_data)
            if isinstance(raw_result, Trajectory):
                trajectory = raw_result
                output = raw_result.final_output
            else:
                output = str(raw_result)
                trajectory = Trajectory(
                    input_prompt=str(input_data),
                    final_output=output
                )
        except Exception as e:
            error_msg = str(e)
            trajectory = Trajectory(
                input_prompt=str(input_data),
                final_output=f"ERROR: {error_msg}"
            )

        return trajectory, output, error_msg

    def run_case(
        self,
        test_case_name: str,
        agent_fn: Callable[[Any], Any],
        input_data: Any,
        evaluators: List[Callable[[Any], MetricScore]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """Run a single test case through an agent function synchronously."""
        start_time = time.time()
        trajectory, output, error_msg = self._execute_agent(agent_fn, input_data)

        metric_scores: List[MetricScore] = []
        
        if error_msg:
            metric_scores.append(MetricScore(
                name="execution_status",
                score=0.0,
                passed=False,
                reason=f"Agent execution raised unhandled error: {error_msg}",
                category="assertion"
            ))
        
        eval_target = trajectory if trajectory else output

        for eval_fn in evaluators:
            try:
                if inspect.iscoroutinefunction(eval_fn):
                    score = asyncio.run(eval_fn(eval_target))
                else:
                    score = eval_fn(eval_target)
                metric_scores.append(score)
            except Exception as ev_err:
                metric_scores.append(MetricScore(
                    name=getattr(eval_fn, "__name__", "evaluator"),
                    score=0.0,
                    passed=False,
                    reason=f"Evaluator threw exception: {str(ev_err)}",
                    category="assertion"
                ))

        all_passed = all(m.passed for m in metric_scores) if metric_scores else not bool(error_msg)
        avg_score = (sum(m.score for m in metric_scores) / len(metric_scores)) if metric_scores else 1.0
        duration_ms = (time.time() - start_time) * 1000.0

        res = EvaluationResult(
            run_id=self.run_id,
            test_case_name=test_case_name,
            trajectory=trajectory,
            metrics=metric_scores,
            passed=all_passed,
            total_score=round(avg_score, 4),
            duration_ms=round(duration_ms, 2),
            metadata=metadata or {}
        )

        self.results.append(res)
        return res

    async def async_run_case(
        self,
        test_case_name: str,
        agent_fn: Callable[[Any], Any],
        input_data: Any,
        evaluators: List[Callable[[Any], MetricScore]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """Run a test case through an agent function asynchronously."""
        start_time = time.time()
        trajectory: Optional[Trajectory] = None
        output = None
        error_msg = None

        try:
            if inspect.iscoroutinefunction(agent_fn):
                raw_result = await agent_fn(input_data)
            else:
                raw_result = agent_fn(input_data)

            if isinstance(raw_result, Trajectory):
                trajectory = raw_result
                output = raw_result.final_output
            else:
                output = str(raw_result)
                trajectory = Trajectory(
                    input_prompt=str(input_data),
                    final_output=output
                )
        except Exception as e:
            error_msg = str(e)
            trajectory = Trajectory(
                input_prompt=str(input_data),
                final_output=f"ERROR: {error_msg}"
            )

        metric_scores: List[MetricScore] = []
        if error_msg:
            metric_scores.append(MetricScore(
                name="execution_status",
                score=0.0,
                passed=False,
                reason=f"Agent execution raised unhandled error: {error_msg}",
                category="assertion"
            ))

        eval_target = trajectory if trajectory else output

        for eval_fn in evaluators:
            try:
                if inspect.iscoroutinefunction(eval_fn):
                    score = await eval_fn(eval_target)
                else:
                    score = eval_fn(eval_target)
                metric_scores.append(score)
            except Exception as ev_err:
                metric_scores.append(MetricScore(
                    name=getattr(eval_fn, "__name__", "evaluator"),
                    score=0.0,
                    passed=False,
                    reason=f"Evaluator threw exception: {str(ev_err)}",
                    category="assertion"
                ))

        all_passed = all(m.passed for m in metric_scores) if metric_scores else not bool(error_msg)
        avg_score = (sum(m.score for m in metric_scores) / len(metric_scores)) if metric_scores else 1.0
        duration_ms = (time.time() - start_time) * 1000.0

        res = EvaluationResult(
            run_id=self.run_id,
            test_case_name=test_case_name,
            trajectory=trajectory,
            metrics=metric_scores,
            passed=all_passed,
            total_score=round(avg_score, 4),
            duration_ms=round(duration_ms, 2),
            metadata=metadata or {}
        )

        self.results.append(res)
        return res

    def save(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Persist evaluation run and results to embedded storage."""
        self.storage.save_run(
            run_id=self.run_id,
            name=self.name,
            results=self.results,
            metadata=metadata
        )
        return self.run_id


def harness(name: Optional[str] = None, db_path: str = ".openharness/evals.db"):
    """Decorator to mark and evaluate agent functions."""
    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            h = Harness(name=name or fn.__name__, db_path=db_path)
            res = fn(*args, **kwargs, harness=h)
            h.save()
            return res
        return wrapper
    return decorator


def eval_case(
    name: str,
    agent_fn: Callable[[Any], Any],
    input_data: Any,
    evaluators: List[Callable[[Any], MetricScore]],
    db_path: str = ".openharness/evals.db"
) -> EvaluationResult:
    """Convenience function to run and save a single evaluation case."""
    h = Harness(name=f"EvalCase: {name}", db_path=db_path)
    res = h.run_case(
        test_case_name=name,
        agent_fn=agent_fn,
        input_data=input_data,
        evaluators=evaluators
    )
    h.save()
    return res
