from typing import Callable, List, Dict, Any
from openharness.core.types import MetricScore, Trajectory


def eval_hallucinated_tools(available_tools: List[str]) -> Callable[[Trajectory], MetricScore]:
    """Evaluator: Detect if the agent attempted to call hallucinated/non-existent tools."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        tool_calls = trajectory.get_tool_calls()
        if not tool_calls:
            return MetricScore(
                name="hallucinated_tools",
                score=1.0,
                passed=True,
                reason="No tool calls executed.",
                category="assertion"
            )

        hallucinated = [tc.name for tc in tool_calls if tc.name not in available_tools]
        if hallucinated:
            return MetricScore(
                name="hallucinated_tools",
                score=0.0,
                passed=False,
                reason=f"Agent attempted to call undefined/hallucinated tools: {hallucinated}",
                category="assertion"
            )

        return MetricScore(
            name="hallucinated_tools",
            score=1.0,
            passed=True,
            reason="All tool calls were valid and defined in available tools.",
            category="assertion"
        )
    return evaluator


def eval_argument_schema(tool_schemas: Dict[str, Dict[str, Any]]) -> Callable[[Trajectory], MetricScore]:
    """Evaluator: Validate parameters of executed tool calls against required schema keys/types."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        tool_calls = trajectory.get_tool_calls()
        invalid_calls = []

        for tc in tool_calls:
            if tc.name in tool_schemas:
                schema = tool_schemas[tc.name]
                required = schema.get("required", [])
                missing = [k for k in required if k not in tc.args]
                if missing:
                    invalid_calls.append(f"{tc.name} (missing required args: {missing})")

        if invalid_calls:
            return MetricScore(
                name="argument_schema",
                score=0.0,
                passed=False,
                reason=f"Tool call argument schema validation failed for: {', '.join(invalid_calls)}",
                category="assertion"
            )

        return MetricScore(
            name="argument_schema",
            score=1.0,
            passed=True,
            reason="All tool calls complied with argument schemas.",
            category="assertion"
        )
    return evaluator


def eval_retry_overflow(max_retries: int = 2) -> Callable[[Trajectory], MetricScore]:
    """Evaluator: Flag excessive tool call retries caused by exceptions or tool failures."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        tool_calls = trajectory.get_tool_calls()
        errored_tools: Dict[str, int] = {}
        overflow = []

        for tc in tool_calls:
            if tc.error:
                errored_tools[tc.name] = errored_tools.get(tc.name, 0) + 1
                if errored_tools[tc.name] > max_retries:
                    overflow.append(f"{tc.name} ({errored_tools[tc.name]} failures)")

        if overflow:
            return MetricScore(
                name="retry_overflow",
                score=0.0,
                passed=False,
                reason=f"Exceeded max retries threshold ({max_retries}) on tools: {', '.join(overflow)}",
                category="trajectory"
            )

        return MetricScore(
            name="retry_overflow",
            score=1.0,
            passed=True,
            reason="Tool retries were within acceptable bounds.",
            category="trajectory"
        )
    return evaluator
