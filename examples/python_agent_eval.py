"""
Example: Evaluating an AI Customer Support Agent with OpenHarness
Demonstrates multi-step tool call tracking, code assertions, trajectory metrics, and local storage.
"""

from openharness import (
    Harness,
    Trajectory,
    Step,
    ToolCall,
    assert_tool_called,
    assert_tool_not_called,
    assert_exact_match,
    eval_goal_completion,
    eval_tool_precision,
    eval_loop_detection,
    eval_step_efficiency
)


def mock_support_agent(user_query: str) -> Trajectory:
    """Simulates a multi-turn agent handling a refund request."""
    step1 = Step(
        step_index=1,
        step_type="tool_call",
        content="Searching for order in database...",
        tool_calls=[ToolCall(name="lookup_order", args={"order_id": "ORD-789"})]
    )
    step2 = Step(
        step_index=2,
        step_type="tool_call",
        content="Issuing refund for order ORD-789...",
        tool_calls=[ToolCall(name="issue_refund", args={"order_id": "ORD-789", "amount": 49.99})]
    )
    step3 = Step(
        step_index=3,
        step_type="agent_response",
        content="Order ORD-789 has been refunded $49.99 successfully."
    )

    return Trajectory(
        name="SupportAgentRun",
        input_prompt=user_query,
        steps=[step1, step2, step3],
        final_output="Order ORD-789 has been refunded $49.99 successfully."
    )


def run_benchmark():
    print("🚀 Running OpenHarness Benchmark for Support Agent...\n")

    h = Harness(name="Customer Support Agent Benchmark v1")

    # Case 1: Standard Refund Flow
    res1 = h.run_case(
        test_case_name="Standard Refund Request",
        agent_fn=mock_support_agent,
        input_data="I'd like a refund for order ORD-789",
        evaluators=[
            assert_tool_called("lookup_order", kwargs={"order_id": "ORD-789"}),
            assert_tool_called("issue_refund"),
            assert_tool_not_called("delete_account"),
            eval_goal_completion(),
            eval_tool_precision(),
            eval_loop_detection(),
            eval_step_efficiency(max_expected_steps=5)
        ]
    )
    print(f"Case 1 ['{res1.test_case_name}']: Passed={res1.passed}, Score={res1.total_score}")

    # Save run to SQLite
    run_id = h.save()
    print(f"\n✅ Benchmark completed! Run ID saved to storage: {run_id}")
    print("View terminal report: harness report")
    print("Launch UI dashboard: harness ui")


if __name__ == "__main__":
    run_benchmark()
