import pytest
from openharness import (
    Trajectory,
    Step,
    ToolCall,
    render_ascii_waterfall,
    render_ascii_scorecard,
    render_svg_waterfall,
    render_pairwise_diff_html,
    EvaluationResult,
    MetricScore
)


def test_visualizations():
    step1 = Step(step_index=1, step_type="tool_call", tool_calls=[ToolCall(name="sql", args={})], duration_ms=120.0)
    step2 = Step(step_index=2, step_type="agent_response", duration_ms=80.0)
    traj = Trajectory(input_prompt="Do query", steps=[step1, step2], total_duration_ms=200.0)

    # ASCII Waterfall
    ascii_out = render_ascii_waterfall(traj)
    assert "WATERFALL TIMELINE" in ascii_out
    assert "Step  1" in ascii_out
    assert "sql" in ascii_out

    # SVG Waterfall
    svg_out = render_svg_waterfall(traj)
    assert "<svg" in svg_out
    assert "Waterfall Timeline" in svg_out

    # ASCII Scorecard
    res = EvaluationResult(
        run_id="run_1",
        test_case_name="TestCase A",
        metrics=[MetricScore(name="m1", score=1.0, passed=True, reason="OK")],
        passed=True,
        total_score=1.0,
        duration_ms=200.0
    )
    scorecard_out = render_ascii_scorecard([res])
    assert "EVALUATION SCORECARD MATRIX" in scorecard_out
    assert "TestCase A" in scorecard_out

    # Pairwise Diff HTML
    diff_html = render_pairwise_diff_html({"name": "Agent A", "passed_count": 1}, {"name": "Agent B", "passed_count": 2})
    assert "Agent A" in diff_html
    assert "Agent B" in diff_html
