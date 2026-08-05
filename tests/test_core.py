import pytest
from openharness import Harness, eval_case, assert_exact_match, assert_tool_called, Trajectory, Step, ToolCall


def sample_agent(query: str):
    step1 = Step(
        step_index=1,
        step_type="tool_call",
        content="Looking up user account details",
        tool_calls=[ToolCall(name="get_user", args={"user_id": "usr_99"})]
    )
    step2 = Step(
        step_index=2,
        step_type="agent_response",
        content="User user_id usr_99 found."
    )
    return Trajectory(
        input_prompt=query,
        steps=[step1, step2],
        final_output="User user_id usr_99 found."
    )


def test_harness_run_case(tmp_path):
    db_file = str(tmp_path / "test_evals.db")
    h = Harness(name="Test Suite", db_path=db_file)
    
    result = h.run_case(
        test_case_name="Lookup User Case",
        agent_fn=sample_agent,
        input_data="Find user usr_99",
        evaluators=[
            assert_exact_match("User user_id usr_99 found."),
            assert_tool_called("get_user", kwargs={"user_id": "usr_99"})
        ]
    )

    assert result.passed is True
    assert result.total_score == 1.0
    assert len(result.metrics) == 2

    # Save to storage
    run_id = h.save()
    assert run_id == h.run_id


def test_eval_case_convenience(tmp_path):
    db_file = str(tmp_path / "test_evals.db")
    result = eval_case(
        name="Simple Case",
        agent_fn=lambda x: "Hello World",
        input_data="Say hello",
        evaluators=[assert_exact_match("Hello World")],
        db_path=db_file
    )
    assert result.passed is True
    assert result.total_score == 1.0
