import pytest
from openharness import (
    Trajectory,
    Step,
    ToolCall,
    eval_code_quality,
    eval_reasoning_depth,
    eval_quality_pareto_index
)


def test_code_quality():
    valid_code = "def add(a, b):\n    return a + b\n"
    score_valid = eval_code_quality()(valid_code)
    assert score_valid.passed is True
    assert score_valid.score == 1.0

    invalid_code = "def bad_syntax(a, b:\n    return a +"
    score_invalid = eval_code_quality()(invalid_code)
    assert score_invalid.passed is False
    assert score_invalid.score == 0.0


def test_reasoning_depth():
    step1 = Step(step_index=1, step_type="thought", content="Analyzing bug...")
    step2 = Step(step_index=2, step_type="tool_call", tool_calls=[ToolCall(name="run_command", args={"command": "pytest"})])
    step3 = Step(step_index=3, step_type="thought", content="Fix verified.")

    traj = Trajectory(input_prompt="Fix bug", steps=[step1, step2, step3], final_output="Fixed")
    score_depth = eval_reasoning_depth()(traj)
    assert score_depth.passed is True
    assert score_depth.score >= 0.7


def test_quality_pareto_index():
    step1 = Step(step_index=1, step_type="tool_call", tool_calls=[ToolCall(name="read_file", args={"path": "a.py"})])
    traj = Trajectory(input_prompt="Read file", steps=[step1], final_output="File contents", total_duration_ms=1200.0)

    score_pareto = eval_quality_pareto_index(min_quality_score=0.8)(traj)
    assert score_pareto.passed is True
    assert "Quality index" in score_pareto.reason
