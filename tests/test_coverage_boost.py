import json
import asyncio
import os
import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

import openharness
from openharness import (
    Harness,
    harness,
    eval_case,
    Trajectory,
    Step,
    ToolCall,
    MetricScore,
    TestCase,
    Dataset,
    assert_tool_called,
    assert_tool_not_called,
    assert_exact_match,
    assert_regex,
    assert_json_schema,
    assert_custom,
    eval_goal_completion,
    eval_tool_precision,
    eval_loop_detection,
    eval_step_efficiency,
    eval_hallucinated_tools,
    eval_argument_schema,
    eval_retry_overflow,
    llm_judge,
    pairwise_arena_judge,
    export_to_junit_xml,
    calculate_trajectory_cost
)
from openharness.providers import BaseProvider, ProviderResponse, get_provider, OllamaProvider, OpenAICompatibleProvider
from openharness.cli.main import cli
from openharness.plugins.pytest_plugin import PytestHarnessPlugin


class MockLLMProvider(BaseProvider):
    def __init__(self, should_fail=False):
        self.should_fail = should_fail

    def generate(self, prompt: str, system_prompt=None, temperature=0.0, max_tokens=1000, **kwargs):
        if self.should_fail:
            raise RuntimeError("LLM Failure simulated")
        return ProviderResponse(
            content='{"score": 0.9, "passed": true, "reason": "Great job"}',
            prompt_tokens=10,
            completion_tokens=20,
            model="mock-model"
        )

    async def agenerate(self, prompt: str, system_prompt=None, temperature=0.0, max_tokens=1000, **kwargs):
        return self.generate(prompt, system_prompt, temperature, max_tokens, **kwargs)


def test_types_methods():
    tc1 = ToolCall(name="tool1", args={"a": 1})
    step1 = Step(step_index=1, step_type="tool_call", tool_calls=[tc1], prompt_tokens=5, completion_tokens=5)
    traj = Trajectory(input_prompt="test", steps=[step1], final_output="out")

    assert traj.get_tool_names() == ["tool1"]
    assert len(traj.get_tool_calls()) == 1


def test_harness_decorator_and_exceptions(tmp_path):
    db_file = str(tmp_path / "dec.db")

    @harness(name="DecSuite", db_path=db_file)
    def my_decorated_fn(input_str, harness=None):
        return harness.run_case("Case 1", lambda x: x, input_str, [assert_exact_match("Hello")])

    res = my_decorated_fn("Hello")
    assert res.passed is True

    # Exception in agent_fn
    h = Harness(name="ErrSuite", db_path=db_file)
    res_err = h.run_case("Crashing Agent", lambda x: 1/0, "query", [assert_exact_match("x")])
    assert res_err.passed is False

    # Coroutine in sync run_case
    async def async_ev(t):
        return MetricScore(name="ev", score=1.0, passed=True, reason="ok")

    res_async_ev = h.run_case("Async Ev Sync Run", lambda x: "ok", "q", [async_ev])
    assert res_async_ev.passed is True

    # Exception in async_run_case
    async def crashing_async_agent(x):
        raise ValueError("Async crash")

    async def run_async_err():
        return await h.async_run_case("Crash Case", crashing_async_agent, "q", [])

    res_async_crash = asyncio.run(run_async_err())
    assert res_async_crash.passed is False


def test_llm_judge_evaluators():
    mock_prov = MockLLMProvider()
    judge_fn = llm_judge(rubric="Polite response", provider=mock_prov)
    
    score_str = judge_fn("Plain string response")
    assert score_str.passed is True

    traj = Trajectory(input_prompt="Hi", final_output="Hello!")
    score = judge_fn(traj)
    assert score.passed is True
    assert score.score == 0.9

    arena_fn = pairwise_arena_judge(rubric="Best response", provider=mock_prov)
    score_arena = arena_fn(traj, traj)
    assert score_arena.category == "llm_judge"

    failing_prov = MockLLMProvider(should_fail=True)
    failing_judge = llm_judge(rubric="r", provider=failing_prov)
    res_fail = failing_judge(traj)
    assert res_fail.passed is False

    failing_arena = pairwise_arena_judge(rubric="r", provider=failing_prov)
    res_arena_fail = failing_arena(traj, traj)
    assert res_arena_fail.score == 0.5


def test_assertions_comprehensive():
    traj = Trajectory(
        input_prompt="test",
        steps=[
            Step(step_index=1, step_type="tool_call", tool_calls=[ToolCall(name="db_query", args={"q": "SELECT 1"})])
        ],
        final_output="Done"
    )

    assert assert_tool_called("db_query", order=5)(traj).passed is False
    assert assert_tool_called("db_query", kwargs={"q": "WRONG"})(traj).passed is False
    assert assert_exact_match("WRONG")(traj).passed is False
    assert assert_regex(r"^NOT_FOUND$")(traj).passed is False
    assert assert_json_schema({"required": ["a"]})("[]").passed is False
    assert assert_json_schema({"required": ["missing_key"]})("{\"a\": 1}").passed is False
    assert assert_custom("chk", lambda t: False)(traj).passed is False
    assert assert_custom("bad_fn", lambda t: 1/0)(traj).passed is False

    assert eval_goal_completion()(Trajectory(input_prompt="q", final_output="")).passed is False
    
    traj_err = Trajectory(
        input_prompt="test",
        steps=[Step(step_index=1, step_type="tool_call", tool_calls=[ToolCall(name="err_tool", args={}, error="Crash")])],
        final_output="Done with error"
    )
    assert eval_goal_completion()(traj_err).score == 0.5

    assert eval_tool_precision()(Trajectory(input_prompt="q", steps=[])).passed is True

    big_steps = [Step(step_index=i) for i in range(15)]
    big_traj = Trajectory(input_prompt="q", steps=big_steps, final_output="done")
    assert eval_step_efficiency(max_expected_steps=5)(big_traj).passed is False


def test_dataset_jsonl_empty_lines(tmp_path):
    jsonl = tmp_path / "empty.jsonl"
    with open(jsonl, "w") as f:
        f.write("\n\n{\"name\": \"c1\", \"input\": \"in1\"}\n\n")
    ds = Dataset.from_jsonl(str(jsonl))
    assert len(ds.cases) == 1


def test_exporters_junit_failure():
    run_detail = {
        "name": "Failed Suite",
        "total_count": 1,
        "failed_count": 1,
        "duration_ms": 50.0,
        "results": [
            {
                "test_case_name": "Failed Case",
                "passed": False,
                "duration_ms": 50.0,
                "metrics": [{"name": "m1", "passed": False, "reason": "Assert failed"}]
            }
        ]
    }
    xml = export_to_junit_xml(run_detail)
    assert "<failure" in xml
    assert "Assert failed" in xml


def test_cli_all_branches(tmp_path):
    runner = CliRunner()
    db_file = str(tmp_path / "cli_test.db")
    h = Harness(name="ExportSuite", db_path=db_file)
    h.run_case("C1", lambda x: "out", "in", [assert_exact_match("out")])
    run_id = h.save()

    res_inv = runner.invoke(cli, ["export", "--run-id", "non_existent_id", "--db", db_file])
    assert res_inv.exit_code != 0

    (tmp_path / "harness_example.py").write_text("existing")
    with patch("os.path.exists", return_value=True):
        res_init = runner.invoke(cli, ["init"])
        assert "already exists" in res_init.output


def test_provider_full_mock():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Ollama OK", "prompt_eval_count": 1, "eval_count": 1}
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        prov = OllamaProvider(model="llama3.1")
        res = prov.generate("hi")
        assert res.content == "Ollama OK"

    with patch("httpx.AsyncClient") as mock_async_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Async Ollama OK", "prompt_eval_count": 1, "eval_count": 1}
        mock_resp.raise_for_status.return_value = None

        async def mock_post(*args, **kwargs):
            return mock_resp

        mock_client.post = mock_post
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client

        prov = OllamaProvider(model="llama3.1")
        res_async = asyncio.run(prov.agenerate("hi"))
        assert res_async.content == "Async Ollama OK"

    # OpenAI sync and async mocks
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "GPT OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5}
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        prov_openai = OpenAICompatibleProvider(model="gpt-4o")
        res_o = prov_openai.generate("hi")
        assert res_o.content == "GPT OK"

    with patch("httpx.AsyncClient") as mock_async_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Async GPT OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5}
        }
        mock_resp.raise_for_status.return_value = None

        async def mock_post(*args, **kwargs):
            return mock_resp

        mock_client.post = mock_post
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client

        prov_openai = OpenAICompatibleProvider(model="gpt-4o")
        res_oa = asyncio.run(prov_openai.agenerate("hi"))
        assert res_oa.content == "Async GPT OK"

    # Provider errors
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client_cls.return_value.__enter__.return_value = mock_client

        prov_err = OllamaProvider()
        with pytest.raises(RuntimeError):
            prov_err.generate("test")

        prov_openai_err = OpenAICompatibleProvider()
        with pytest.raises(RuntimeError):
            prov_openai_err.generate("test")

    with patch("httpx.AsyncClient") as mock_async_client_cls:
        mock_client = MagicMock()
        async def mock_post_err(*args, **kwargs):
            raise Exception("Async error")
        mock_client.post = mock_post_err
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client

        prov_err = OllamaProvider()
        with pytest.raises(RuntimeError):
            asyncio.run(prov_err.agenerate("test"))

        prov_openai_err = OpenAICompatibleProvider()
        with pytest.raises(RuntimeError):
            asyncio.run(prov_openai_err.agenerate("test"))


def test_pytest_plugin(tmp_path):
    db_file = str(tmp_path / "pytest.db")
    plugin = PytestHarnessPlugin(db_path=db_file)

    class MockItem:
        name = "test_foo"

    class MockReport:
        when = "call"
        passed = True
        duration = 0.05
        outcome = "passed"

    class MockOutcome:
        def get_result(self):
            return MockReport()

    gen = plugin.pytest_runtest_makereport(MockItem(), None)
    next(gen)
    try:
        gen.send(MockOutcome())
    except StopIteration:
        pass

    assert len(plugin.results) == 1
    assert plugin.results[0].test_case_name == "test_foo"

    class MockConfig:
        rootpath = MagicMock()
        rootpath.name = "MyProject"

    class MockSession:
        config = MockConfig()

    plugin.pytest_sessionfinish(MockSession(), 0)
    assert len(plugin.storage.get_runs()) == 1
