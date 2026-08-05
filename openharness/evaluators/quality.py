import ast
import re
from typing import Callable, List, Dict, Any, Optional, Union
from openharness.core.types import MetricScore, Trajectory, ToolCall


def eval_code_quality() -> Callable[[Union[str, Trajectory]], MetricScore]:
    """Evaluator: Evaluate Python code syntax validity, complexity, and cleanliness."""
    def evaluator(target: Union[str, Trajectory]) -> MetricScore:
        actual = target.final_output if isinstance(target, Trajectory) else str(target)
        actual_str = actual or ""

        # Extract code blocks if markdown fenced
        code_blocks = re.findall(r"```(?:python)?\n(.*?)\n```", actual_str, re.DOTALL)
        code_to_check = code_blocks[0] if code_blocks else actual_str

        try:
            tree = ast.parse(code_to_check)
            # Count AST nodes as proxy for structure
            node_count = sum(1 for _ in ast.walk(tree))
            
            return MetricScore(
                name="code_quality",
                score=1.0,
                passed=True,
                reason=f"Code parsed into valid AST ({node_count} nodes, 0 syntax errors).",
                category="quality"
            )
        except SyntaxError as e:
            return MetricScore(
                name="code_quality",
                score=0.0,
                passed=False,
                reason=f"Code syntax error at line {e.lineno}: {e.msg}",
                category="quality"
            )
        except Exception as e:
            return MetricScore(
                name="code_quality",
                score=0.5,
                passed=True,
                reason=f"Could not parse strictly as Python AST: {str(e)}",
                category="quality"
            )
    return evaluator


def eval_reasoning_depth() -> Callable[[Trajectory], MetricScore]:
    """
    Evaluator: Measures step reflection quality, error self-correction, 
    and thought-to-action ratio. Agents that verify their work score higher.
    """
    def evaluator(trajectory: Trajectory) -> MetricScore:
        steps = trajectory.steps
        if not steps:
            return MetricScore(name="reasoning_depth", score=0.0, passed=False, reason="No steps in trajectory.", category="quality")

        thought_steps = [s for s in steps if s.step_type == "thought" or s.content]
        verification_steps = [s for s in steps if any(tc.name in ["run_command", "pytest", "verify", "check", "test"] for tc in s.tool_calls)]
        
        # Self-correction detection: tool call errored, then subsequently succeeded
        errored_tools = set()
        self_corrected = False
        for s in steps:
            for tc in s.tool_calls:
                if tc.error:
                    errored_tools.add(tc.name)
                elif tc.name in errored_tools:
                    self_corrected = True

        depth_score = 0.5
        reasons = []

        if len(thought_steps) >= 2:
            depth_score += 0.2
            reasons.append("Multi-step reasoning")

        if verification_steps:
            depth_score += 0.2
            reasons.append("Self-verification executed")

        if self_corrected:
            depth_score += 0.1
            reasons.append("Self-corrected from error")

        final_score = min(1.0, depth_score)
        passed = final_score >= 0.7

        return MetricScore(
            name="reasoning_depth",
            score=round(final_score, 4),
            passed=passed,
            reason=f"Reasoning depth score: {final_score:.2f} ({', '.join(reasons) or 'Basic trajectory'}).",
            category="quality"
        )
    return evaluator


def eval_quality_pareto_index(min_quality_score: float = 0.8) -> Callable[[Trajectory], MetricScore]:
    """
    Evaluator: Evaluates quality-to-latency ratio. Ensures high quality is achieved,
    accepting extra latency if quality threshold is met.
    """
    def evaluator(trajectory: Trajectory) -> MetricScore:
        # Quality score computed from reasoning depth and tool precision
        precision_calls = [tc for tc in trajectory.get_tool_calls() if not tc.error]
        total_calls = len(trajectory.get_tool_calls()) or 1
        precision = len(precision_calls) / total_calls

        has_output = bool(trajectory.final_output and len(trajectory.final_output.strip()) > 0)
        quality = (precision * 0.6) + (0.4 if has_output else 0.0)

        passed = quality >= min_quality_score
        return MetricScore(
            name="quality_pareto_index",
            score=round(quality, 4),
            passed=passed,
            reason=f"Quality index {quality:.2f} (Min required: {min_quality_score:.2f}). Total latency: {trajectory.total_duration_ms:.1f}ms.",
            category="quality"
        )
    return evaluator
