from typing import Callable, List, Optional, Dict, Any
from openharness.core.types import MetricScore, Trajectory


def eval_goal_completion() -> Callable[[Trajectory], MetricScore]:
    """Trajectory Metric: Verify agent finished with non-empty final output and no uncaught exceptions."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        if not trajectory.final_output or len(trajectory.final_output.strip()) == 0:
            return MetricScore(
                name="goal_completion",
                score=0.0,
                passed=False,
                reason="Agent trajectory terminated without providing a final answer.",
                category="trajectory"
            )
        
        # Check if last step indicates error
        has_error = any(tc.error for tc in trajectory.get_tool_calls())
        if has_error:
            error_tools = [tc.name for tc in trajectory.get_tool_calls() if tc.error]
            return MetricScore(
                name="goal_completion",
                score=0.5,
                passed=True,
                reason=f"Goal completed with output, but encountered tool errors in: {error_tools}",
                category="trajectory"
            )

        return MetricScore(
            name="goal_completion",
            score=1.0,
            passed=True,
            reason="Goal successfully completed without tool errors.",
            category="trajectory"
        )
    return evaluator


def eval_tool_precision() -> Callable[[Trajectory], MetricScore]:
    """Trajectory Metric: Ratio of error-free tool calls to total tool calls executed."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        tool_calls = trajectory.get_tool_calls()
        if not tool_calls:
            return MetricScore(
                name="tool_precision",
                score=1.0,
                passed=True,
                reason="No tools executed in trajectory.",
                category="trajectory"
            )

        successful = sum(1 for tc in tool_calls if not tc.error)
        total = len(tool_calls)
        precision = successful / total
        passed = precision >= 0.8

        return MetricScore(
            name="tool_precision",
            score=round(precision, 4),
            passed=passed,
            reason=f"{successful}/{total} tool calls executed successfully ({precision*100:.1f}% precision).",
            category="trajectory"
        )
    return evaluator


def eval_loop_detection(max_repeats: int = 2) -> Callable[[Trajectory], MetricScore]:
    """Trajectory Metric: Detects stuck agents repeating identical tool calls with identical arguments."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        tool_calls = trajectory.get_tool_calls()
        seen: Dict[str, int] = {}
        loop_found = False
        loop_detail = ""

        for tc in tool_calls:
            # Create hashable key from tool name and JSON stringified args
            key = f"{tc.name}:{str(sorted(tc.args.items()))}"
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > max_repeats:
                loop_found = True
                loop_detail = f"Tool '{tc.name}' called with identical args {tc.args} {seen[key]} times."
                break

        if loop_found:
            return MetricScore(
                name="loop_detection",
                score=0.0,
                passed=False,
                reason=f"Agent loop detected! {loop_detail}",
                category="trajectory"
            )

        return MetricScore(
            name="loop_detection",
            score=1.0,
            passed=True,
            reason="No repeating tool loops detected.",
            category="trajectory"
        )
    return evaluator


def eval_step_efficiency(max_expected_steps: int = 10) -> Callable[[Trajectory], MetricScore]:
    """Trajectory Metric: Evaluate efficiency based on number of trajectory steps taken."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        step_count = len(trajectory.steps)
        if step_count <= max_expected_steps:
            score = 1.0
            passed = True
            reason = f"Agent completed task in {step_count} steps (within max threshold of {max_expected_steps})."
        else:
            overflow = step_count - max_expected_steps
            score = max(0.0, 1.0 - (overflow * 0.1))
            passed = score >= 0.5
            reason = f"Agent took {step_count} steps, exceeding max threshold of {max_expected_steps}."

        return MetricScore(
            name="step_efficiency",
            score=round(score, 4),
            passed=passed,
            reason=reason,
            category="trajectory"
        )
    return evaluator
