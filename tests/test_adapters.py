import pytest
from openharness.adapters.langchain import OpenHarnessLangChainCallbackHandler
from openharness.adapters.llamaindex import OpenHarnessLlamaIndexHandler
from openharness.adapters.autogen import OpenHarnessAutoGenTracer
from openharness.adapters.swarm import OpenHarnessSwarmTracer


def test_langchain_adapter():
    handler = OpenHarnessLangChainCallbackHandler(name="LangChain Test")
    handler.on_llm_start({"name": "gpt-4o"}, ["What is the capital of France?"])
    handler.on_tool_start({"name": "search"}, "capital of france")
    handler.on_tool_end("Paris")
    handler.on_chain_end({"output": "Paris is the capital of France."})

    traj = handler.get_trajectory()
    assert traj.name == "LangChain Test"
    assert traj.input_prompt == "What is the capital of France?"
    assert len(traj.steps) == 2
    assert traj.final_output == "Paris is the capital of France."


def test_llamaindex_adapter():
    handler = OpenHarnessLlamaIndexHandler(name="LlamaIndex Test")
    handler.on_event("llm", {"prompt": "Query doc"})
    handler.on_event("function_call", {"name": "retriever", "args": {"top_k": 3}})
    traj = handler.finish("Found answer")

    assert len(traj.steps) == 2
    assert traj.final_output == "Found answer"


def test_autogen_adapter():
    tracer = OpenHarnessAutoGenTracer(name="AutoGen Test")
    messages = [
        {"role": "user", "name": "UserProxy", "content": "Calculate 2+2"},
        {"role": "assistant", "name": "Assistant", "content": "4", "function_call": {"name": "calculator", "arguments": {"expr": "2+2"}}}
    ]
    traj = tracer.trace_messages(messages)
    assert len(traj.steps) == 2
    assert traj.final_output == "4"


def test_swarm_adapter():
    class MockSwarmResponse:
        agent = type("Agent", (), {"name": "SalesAgent"})()
        messages = [
            {"content": "Transferring to RefundAgent", "tool_calls": [{"function": {"name": "issue_refund", "arguments": {"id": 1}}}]}
        ]

    tracer = OpenHarnessSwarmTracer(name="Swarm Test")
    traj = tracer.trace_response(MockSwarmResponse())
    assert len(traj.steps) == 1
    assert traj.steps[0].tool_calls[0].name == "issue_refund"
