import pytest
from openharness import (
    Harness,
    Trajectory,
    Step,
    ToolCall,
    assert_tool_called,
    eval_goal_completion,
    eval_tool_precision,
    eval_loop_detection,
    eval_step_efficiency,
    eval_hallucinated_tools,
    eval_argument_schema,
    run_determinism_sweep
)


def mock_coding_agent(user_request: str) -> Trajectory:
    step1 = Step(
        step_index=1,
        step_type="tool_call",
        content="Searching for buggy function definition",
        tool_calls=[ToolCall(name="grep_search", args={"query": "def parse_config"})],
        duration_ms=45.0
    )
    step2 = Step(
        step_index=2,
        step_type="tool_call",
        content="Reading file config_parser.py",
        tool_calls=[ToolCall(name="read_file", args={"path": "config_parser.py"})],
        duration_ms=30.0
    )
    step3 = Step(
        step_index=3,
        step_type="tool_call",
        content="Applying fix to parse_config function",
        tool_calls=[ToolCall(name="replace_file_content", args={"path": "config_parser.py", "target": "a", "replacement": "b"})],
        duration_ms=65.0
    )
    step4 = Step(
        step_index=4,
        step_type="tool_call",
        content="Running pytest test suite",
        tool_calls=[ToolCall(name="run_command", args={"command": "pytest tests/"}, result="4 passed")],
        duration_ms=180.0
    )
    step5 = Step(
        step_index=5,
        step_type="agent_response",
        content="Fixed bug in config_parser.py.",
        duration_ms=25.0
    )

    return Trajectory(
        name="CodingAgentRepairRun",
        input_prompt=user_request,
        steps=[step1, step2, step3, step4, step5],
        final_output="Fixed bug in config_parser.py."
    )


def test_agentic_coding_benchmark(tmp_path):
    db_file = str(tmp_path / "coding_eval.db")
    h = Harness("Coding Agent Suite", db_path=db_file)

    available_tools = ["read_file", "write_file", "replace_file_content", "grep_search", "run_command"]
    tool_schemas = {
        "read_file": {"required": ["path"]},
        "replace_file_content": {"required": ["path", "target", "replacement"]},
        "run_command": {"required": ["command"]}
    }

    res = h.run_case(
        test_case_name="Fix Config Bug",
        agent_fn=mock_coding_agent,
        input_data="Fix config bug",
        evaluators=[
            assert_tool_called("grep_search"),
            assert_tool_called("replace_file_content"),
            assert_tool_called("run_command"),
            eval_goal_completion(),
            eval_tool_precision(),
            eval_loop_detection(),
            eval_step_efficiency(max_expected_steps=8),
            eval_hallucinated_tools(available_tools),
            eval_argument_schema(tool_schemas)
        ]
    )

    assert res.passed is True
    assert res.total_score == 1.0
    assert len(res.metrics) == 9

    sweep = run_determinism_sweep(
        test_case_name="Coding Determinism",
        agent_fn=mock_coding_agent,
        input_data="Fix bug",
        evaluators=[eval_goal_completion()],
        n_runs=3,
        db_path=db_file
    )

    assert sweep.pass_rate == 1.0
    assert sweep.flakiness_score == 0.0
