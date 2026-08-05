"""
Example: Tracing and Evaluating a LangChain Agent with OpenHarness
"""

from openharness import Harness, assert_tool_called, eval_goal_completion
from openharness.adapters.langchain import OpenHarnessLangChainCallbackHandler


def run_langchain_agent_evaluation():
    print("🚀 Tracing LangChain Agent run with OpenHarness...\n")

    # 1. Initialize OpenHarness LangChain Callback Handler
    handler = OpenHarnessLangChainCallbackHandler(name="LangChain Search Agent")

    # 2. Simulate LangChain Execution Events
    handler.on_llm_start({"name": "gpt-4o"}, ["Find weather in Tokyo"])
    handler.on_tool_start({"name": "get_weather"}, "Tokyo")
    handler.on_tool_end("22°C, Clear Sky")
    handler.on_chain_end({"output": "The weather in Tokyo is currently 22°C and clear."})

    # 3. Extract Trajectory object
    trajectory = handler.get_trajectory()

    # 4. Evaluate with OpenHarness
    h = Harness("LangChain Benchmark Suite")
    res = h.run_case(
        test_case_name="Tokyo Weather Query",
        agent_fn=lambda input_data: trajectory,  # Pass trajectory directly
        input_data="Find weather in Tokyo",
        evaluators=[
            assert_tool_called("get_weather"),
            eval_goal_completion()
        ]
    )

    h.save()
    print(f"Eval result: Passed={res.passed}, Score={res.total_score}")


if __name__ == "__main__":
    run_langchain_agent_evaluation()
