import pytest
from openharness import (
    Trajectory,
    Step,
    ToolCall,
    eval_hallucinated_tools,
    eval_argument_schema,
    eval_retry_overflow
)


def test_hallucinated_tools():
    traj = Trajectory(
        input_prompt="Do something",
        steps=[
            Step(step_index=1, step_type="tool_call", tool_calls=[ToolCall(name="valid_tool", args={})]),
            Step(step_index=2, step_type="tool_call", tool_calls=[ToolCall(name="fake_tool", args={})])
        ]
    )

    eval_fn = eval_hallucinated_tools(available_tools=["valid_tool", "other_tool"])
    score = eval_fn(traj)
    assert score.passed is False
    assert "fake_tool" in score.reason


def test_argument_schema():
    traj = Trajectory(
        input_prompt="Search user",
        steps=[
            Step(step_index=1, step_type="tool_call", tool_calls=[ToolCall(name="search_user", args={"age": 25})])
        ]
    )

    schemas = {"search_user": {"required": ["user_id"]}}
    score = eval_argument_schema(schemas)(traj)
    assert score.passed is False
    assert "user_id" in score.reason


def test_retry_overflow():
    traj = Trajectory(
        input_prompt="Retry test",
        steps=[
            Step(step_index=1, step_type="tool_call", tool_calls=[ToolCall(name="db", args={}, error="Timeout")]),
            Step(step_index=2, step_type="tool_call", tool_calls=[ToolCall(name="db", args={}, error="Timeout")]),
            Step(step_index=3, step_type="tool_call", tool_calls=[ToolCall(name="db", args={}, error="Timeout")])
        ]
    )

    score = eval_retry_overflow(max_retries=2)(traj)
    assert score.passed is False
