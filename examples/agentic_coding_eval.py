"""
Real-World Agentic Coding Benchmark: Autonomous Code Repair Agent
Evaluates multi-turn tool invocation, code patch accuracy, retry recovery, and determinism.
"""

from openharness import (
    Harness,
    Trajectory,
    Step,
    ToolCall,
    assert_tool_called,
    assert_tool_not_called,
    assert_regex,
    eval_goal_completion,
    eval_tool_precision,
    eval_loop_detection,
    eval_step_efficiency,
    eval_hallucinated_tools,
    eval_argument_schema,
    eval_retry_overflow,
    eval_safety_and_jailbreak,
    eval_cost_budget,
    run_determinism_sweep
)


def mock_coding_agent(user_request: str) -> Trajectory:
    """Simulates an autonomous coding agent diagnosing and fixing a bug."""
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
        tool_calls=[ToolCall(name="replace_file_content", args={"path": "config_parser.py", "target": "return json.loads(data)", "replacement": "return json.loads(data) if data else {}"})],
        duration_ms=65.0
    )
    step4 = Step(
        step_index=4,
        step_type="tool_call",
        content="Running pytest test suite",
        tool_calls=[ToolCall(name="run_command", args={"command": "pytest tests/"}, result="4 passed in 0.12s")],
        duration_ms=180.0
    )
    step5 = Step(
        step_index=5,
        step_type="agent_response",
        content="Fixed bug in config_parser.py. All 4 unit tests passing.",
        duration_ms=25.0
    )

    return Trajectory(
        name="CodingAgentRepairRun",
        input_prompt=user_request,
        steps=[step1, step2, step3, step4, step5],
        final_output="Fixed bug in config_parser.py. All 4 unit tests passing.",
        total_duration_ms=345.0,
        total_prompt_tokens=450,
        total_completion_tokens=180
    )


def run_coding_benchmark():
    print("🚀 Running OpenHarness Real-World Agentic Coding Benchmark...\n")

    h = Harness(name="Agentic Coding Evaluation Suite")

    available_tools = ["read_file", "write_file", "replace_file_content", "grep_search", "run_command"]
    tool_schemas = {
        "read_file": {"required": ["path"]},
        "replace_file_content": {"required": ["path", "target", "replacement"]},
        "run_command": {"required": ["command"]}
    }

    res = h.run_case(
        test_case_name="Fix Empty JSON Config Parsing Bug",
        agent_fn=mock_coding_agent,
        input_data="Fix ValueError when parsing empty config files in config_parser.py",
        evaluators=[
            assert_tool_called("grep_search", kwargs={"query": "def parse_config"}),
            assert_tool_called("replace_file_content"),
            assert_tool_called("run_command", kwargs={"command": "pytest tests/"}),
            assert_tool_not_called("delete_file"),
            assert_regex(r"Fixed bug in config_parser\.py"),
            eval_goal_completion(),
            eval_tool_precision(),
            eval_loop_detection(),
            eval_step_efficiency(max_expected_steps=8),
            eval_hallucinated_tools(available_tools),
            eval_argument_schema(tool_schemas),
            eval_retry_overflow(max_retries=2),
            eval_safety_and_jailbreak(),
            eval_cost_budget(max_cost_usd=0.01)
        ]
    )

    print(f"Test Case: '{res.test_case_name}'")
    print(f"Passed: {res.passed} | Score: {res.total_score} | Duration: {res.duration_ms}ms\n")

    for m in res.metrics:
        symbol = "✔" if m.passed else "✖"
        print(f"  {symbol} [{m.category}] {m.name}: {m.reason}")

    h.save()

    print("\n🔄 Running Determinism Sweep (5 runs)...")
    sweep = run_determinism_sweep(
        test_case_name="Coding Repair Determinism",
        agent_fn=mock_coding_agent,
        input_data="Fix empty JSON config bug",
        evaluators=[assert_tool_called("run_command"), eval_goal_completion()],
        n_runs=5
    )

    print(f"Sweep Pass Rate: {sweep.pass_rate * 100}% | Flakiness Score: {sweep.flakiness_score} (0.0 = Stable)")
    print("\n✅ Real-World Coding Benchmark Completed!")


if __name__ == "__main__":
    run_coding_benchmark()
