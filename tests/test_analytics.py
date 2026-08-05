import pytest
from openharness import (
    Trajectory,
    Step,
    ToolCall,
    calculate_trajectory_cost,
    calculate_latency_breakdown
)


def test_analytics():
    traj = Trajectory(
        input_prompt="Test query",
        steps=[
            Step(
                step_index=1,
                step_type="tool_call",
                prompt_tokens=100,
                completion_tokens=50,
                duration_ms=200.0,
                tool_calls=[ToolCall(name="search", args={}, duration_ms=150.0)]
            )
        ],
        total_duration_ms=300.0
    )

    cost = calculate_trajectory_cost(traj, default_model="gpt-4o-mini")
    assert cost.prompt_tokens == 100
    assert cost.completion_tokens == 50
    assert cost.total_tokens == 150
    assert cost.total_cost_usd > 0.0

    latency = calculate_latency_breakdown(traj)
    assert latency.total_duration_ms == 300.0
    assert latency.tool_duration_ms == 150.0
    assert latency.agent_reasoning_duration_ms == 150.0
