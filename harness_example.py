from openharness import eval_case, assert_tool_called, assert_exact_match, eval_goal_completion

def my_simple_agent(user_query: str):
    return "Refund processed for order #12345"

def test_refund():
    result = eval_case(
        name="Refund Agent Test",
        agent_fn=my_simple_agent,
        input_data="Issue refund for order #12345",
        evaluators=[
            assert_exact_match("Refund processed for order #12345"),
            eval_goal_completion()
        ]
    )
    print(f"Eval Result: Passed={result.passed}, Score={result.total_score}")

if __name__ == "__main__":
    test_refund()
