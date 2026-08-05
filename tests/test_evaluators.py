import pytest
from openharness.core.types import Trajectory, Step, ToolCall
from openharness.evaluators.assertions import (
    assert_tool_called,
    assert_tool_not_called,
    assert_exact_match,
    assert_regex,
    assert_json_schema,
    assert_custom
)
from openharness.evaluators.trajectory import (
    eval_goal_completion,
    eval_tool_precision,
    eval_loop_detection,
    eval_step_efficiency
)


def create_sample_trajectory(tool_names=["fetch_data", "process_data"]):
    steps = []
    for idx, tname in enumerate(tool_names, 1):
        steps.append(Step(
            step_index=idx,
            step_type="tool_call",
            tool_calls=[ToolCall(name=tname, args={"id": idx})]
        ))
    return Trajectory(
        input_prompt="Do task",
        steps=steps,
        final_output="Task completed successfully."
    )


def test_assertions():
    traj = create_sample_trajectory(["search", "database_query"])
    
    score_tool = assert_tool_called("search")(traj)
    assert score_tool.passed is True

    score_not_called = assert_tool_not_called("delete_all")(traj)
    assert score_not_called.passed is True

    score_exact = assert_exact_match("Task completed successfully.")(traj)
    assert score_exact.passed is True

    score_regex = assert_regex(r"completed.*successfully")(traj)
    assert score_regex.passed is True

    schema = {"required": ["status"]}
    score_json = assert_json_schema(schema)("{\"status\": \"ok\"}")
    assert score_json.passed is True


def test_trajectory_evaluators():
    traj = create_sample_trajectory(["fetch", "calc"])
    
    assert eval_goal_completion()(traj).passed is True
    assert eval_tool_precision()(traj).passed is True
    assert eval_loop_detection()(traj).passed is True
    assert eval_step_efficiency(max_expected_steps=5)(traj).passed is True

    # Test loop detection failure
    loop_steps = [
        Step(step_index=1, step_type="tool_call", tool_calls=[ToolCall(name="retry", args={"a": 1})]),
        Step(step_index=2, step_type="tool_call", tool_calls=[ToolCall(name="retry", args={"a": 1})]),
        Step(step_index=3, step_type="tool_call", tool_calls=[ToolCall(name="retry", args={"a": 1})])
    ]
    loop_traj = Trajectory(input_prompt="Loop test", steps=loop_steps, final_output="Stuck")
    assert eval_loop_detection(max_repeats=2)(loop_traj).passed is False
