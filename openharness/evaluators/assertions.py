"""
Assertions module for OpenHarness.
Provides core functionality for the assertions subsystem.
"""
import re
import json
from typing import Any, Callable, Dict, List, Optional, Union
from openharness.core.types import MetricScore, Trajectory, ToolCall


def assert_tool_called(
    tool_name: str,
    kwargs: Optional[Dict[str, Any]] = None,
    order: Optional[int] = None
) -> Callable[[Trajectory], MetricScore]:
    """Assertion: Verify that a specific tool was called by the agent during trajectory."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        tool_calls = trajectory.get_tool_calls()
        matching_calls = [tc for tc in tool_calls if tc.name == tool_name]

        if not matching_calls:
            return MetricScore(
                name=f"tool_called:{tool_name}",
                score=0.0,
                passed=False,
                reason=f"Tool '{tool_name}' was never called. Executed tools: {trajectory.get_tool_names()}",
                category="assertion"
            )

        if kwargs:
            arg_matched = False
            for tc in matching_calls:
                # Check if all specified kwargs match tool args
                if all(tc.args.get(k) == v for k, v in kwargs.items()):
                    arg_matched = True
                    break
            if not arg_matched:
                return MetricScore(
                    name=f"tool_called:{tool_name}",
                    score=0.0,
                    passed=False,
                    reason=f"Tool '{tool_name}' was called, but arguments did not match {kwargs}. Actual calls: {[tc.args for tc in matching_calls]}",
                    category="assertion"
                )

        if order is not None:
            if order < 0 or order >= len(tool_calls) or tool_calls[order].name != tool_name:
                actual_order_name = tool_calls[order].name if 0 <= order < len(tool_calls) else "N/A"
                return MetricScore(
                    name=f"tool_called:{tool_name}",
                    score=0.0,
                    passed=False,
                    reason=f"Tool '{tool_name}' was not called at position {order}. Found tool '{actual_order_name}'.",
                    category="assertion"
                )

        return MetricScore(
            name=f"tool_called:{tool_name}",
            score=1.0,
            passed=True,
            reason=f"Tool '{tool_name}' was successfully called with expected criteria.",
            category="assertion"
        )

    return evaluator


def assert_tool_not_called(tool_name: str) -> Callable[[Trajectory], MetricScore]:
    """Assertion: Verify that a forbidden tool was NEVER called."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        executed_tools = trajectory.get_tool_names()
        if tool_name in executed_tools:
            return MetricScore(
                name=f"tool_not_called:{tool_name}",
                score=0.0,
                passed=False,
                reason=f"Forbidden tool '{tool_name}' was executed.",
                category="assertion"
            )
        return MetricScore(
            name=f"tool_not_called:{tool_name}",
            score=1.0,
            passed=True,
            reason=f"Tool '{tool_name}' was correctly omitted.",
            category="assertion"
        )
    return evaluator


def assert_exact_match(expected: str) -> Callable[[Union[str, Trajectory]], MetricScore]:
    """Assertion: Exact match on agent's final output."""
    def evaluator(target: Union[str, Trajectory]) -> MetricScore:
        actual = target.final_output if isinstance(target, Trajectory) else str(target)
        actual_str = (actual or "").strip()
        expected_str = expected.strip()
        passed = actual_str == expected_str
        return MetricScore(
            name="exact_match",
            score=1.0 if passed else 0.0,
            passed=passed,
            reason="Output matches expected string." if passed else f"Expected '{expected_str}', but got '{actual_str}'",
            category="assertion"
        )
    return evaluator


def assert_regex(pattern: str, flags: int = 0) -> Callable[[Union[str, Trajectory]], MetricScore]:
    """Assertion: Match regex pattern on final agent output."""
    regex = re.compile(pattern, flags)
    def evaluator(target: Union[str, Trajectory]) -> MetricScore:
        actual = target.final_output if isinstance(target, Trajectory) else str(target)
        passed = bool(regex.search(actual or ""))
        return MetricScore(
            name=f"regex_match:{pattern}",
            score=1.0 if passed else 0.0,
            passed=passed,
            reason=f"Output matches regex pattern '{pattern}'." if passed else f"Regex '{pattern}' did not match output: '{actual}'",
            category="assertion"
        )
    return evaluator


def assert_json_schema(schema: Dict[str, Any]) -> Callable[[Union[str, Trajectory]], MetricScore]:
    """Assertion: Validate final output is valid JSON adhering to given keys/schema."""
    def evaluator(target: Union[str, Trajectory]) -> MetricScore:
        actual = target.final_output if isinstance(target, Trajectory) else str(target)
        try:
            parsed = json.loads(actual or "")
            if not isinstance(parsed, dict):
                return MetricScore(name="json_schema", score=0.0, passed=False, reason="Output is valid JSON but not a JSON object (dict).", category="assertion")
            
            # Key validation
            required_keys = schema.get("required", [])
            missing = [k for k in required_keys if k not in parsed]
            if missing:
                return MetricScore(name="json_schema", score=0.0, passed=False, reason=f"JSON missing required keys: {missing}", category="assertion")
                
            return MetricScore(name="json_schema", score=1.0, passed=True, reason="JSON matches schema.", category="assertion")
        except Exception as e:
            return MetricScore(name="json_schema", score=0.0, passed=False, reason=f"Failed to parse output as JSON: {str(e)}", category="assertion")
    return evaluator


def assert_custom(name: str, check_fn: Callable[[Trajectory], bool], reason_if_failed: str = "Custom assertion failed") -> Callable[[Trajectory], MetricScore]:
    """Assertion: Wrapper for user-defined Python function assertions."""
    def evaluator(trajectory: Trajectory) -> MetricScore:
        try:
            passed = bool(check_fn(trajectory))
            return MetricScore(
                name=f"custom:{name}",
                score=1.0 if passed else 0.0,
                passed=passed,
                reason="Custom check passed." if passed else reason_if_failed,
                category="assertion"
            )
        except Exception as e:
            return MetricScore(
                name=f"custom:{name}",
                score=0.0,
                passed=False,
                reason=f"Custom assertion threw exception: {str(e)}",
                category="assertion"
            )
    return evaluator
