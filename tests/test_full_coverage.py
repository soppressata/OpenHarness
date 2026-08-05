import json
import asyncio
import os
import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from openharness import (
    Harness,
    Trajectory,
    Step,
    ToolCall,
    MetricScore,
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
    eval_semantic_similarity,
    eval_factuality_and_hallucination,
    eval_safety_and_jailbreak,
    eval_cost_budget,
    calculate_trajectory_cost,
    calculate_latency_breakdown,
    export_to_html,
    export_to_junit_xml,
    render_ascii_waterfall,
    render_svg_waterfall,
    render_pairwise_diff_html
)
from openharness.providers import (
    get_provider,
    OllamaProvider,
    OpenAICompatibleProvider,
    BaseProvider,
    ProviderResponse
)
from openharness.cli.main import cli
from openharness.adapters.langchain import OpenHarnessLangChainCallbackHandler
from openharness.server.app import create_app
from fastapi.testclient import TestClient


def test_provider_factory_branches():
    p_vllm = get_provider("vllm/qwen2.5")
    assert isinstance(p_vllm, OpenAICompatibleProvider)

    p_openai = get_provider("openai/gpt-4o")
    assert isinstance(p_openai, OpenAICompatibleProvider)

    p_ollama = get_provider("ollama/llama3.1")
    assert isinstance(p_ollama, OllamaProvider)

    p_http_ollama = get_provider("http://localhost:11434")
    assert isinstance(p_http_ollama, OllamaProvider)

    p_http_custom = get_provider("http://custom-server:8000")
    assert isinstance(p_http_custom, OpenAICompatibleProvider)

    p_obj = get_provider(p_ollama)
    assert p_obj == p_ollama


def test_langchain_adapter_error():
    handler = OpenHarnessLangChainCallbackHandler("Err LC")
    handler.on_tool_start({"name": "failing_tool"}, "input")
    handler.on_tool_error(RuntimeError("Tool failed"))
    
    traj = handler.get_trajectory()
    assert traj.steps[0].tool_calls[0].error == "Tool failed"


def test_server_export_formats(tmp_path):
    db_file = str(tmp_path / "server_exp.db")
    h = Harness("Server Exp Suite", db_path=db_file)
    h.run_case("C1", lambda x: "ans", "in", [assert_exact_match("ans")])
    run_id = h.save()

    app = create_app(db_path=db_file)
    client = TestClient(app)

    # HTML export
    res_html = client.get(f"/api/runs/{run_id}/export?format=html")
    assert res_html.status_code == 200
    assert "OpenHarness Evaluation Report" in res_html.text

    # JUnit export
    res_junit = client.get(f"/api/runs/{run_id}/export?format=junit")
    assert res_junit.status_code == 200
    assert "<testsuite" in res_junit.text

    # Delete run
    res_del = client.delete(f"/api/runs/{run_id}")
    assert res_del.status_code == 200

    # Delete 404
    assert client.delete(f"/api/runs/{run_id}").status_code == 404


def test_cli_ui_and_synthetic_commands(tmp_path):
    runner = CliRunner()
    db_file = str(tmp_path / "cli_ui.db")

    # Test synthetic command
    out_jsonl = str(tmp_path / "syn.jsonl")
    with patch("openharness.cli.main.generate_synthetic_dataset") as mock_gen:
        from openharness import Dataset
        ds_mock = Dataset("synthetic", cases=[])
        mock_gen.return_value = ds_mock

        res_syn = runner.invoke(cli, ["synthetic", "--prompt", "Domain", "--n-cases", "2", "--out", out_jsonl])
        assert res_syn.exit_code == 0
        assert "Generated synthetic dataset" in res_syn.output

    # Test ui command mock
    with patch("uvicorn.run") as mock_uvicorn:
        res_ui = runner.invoke(cli, ["ui", "--port", "8502", "--db", db_file])
        assert res_ui.exit_code == 0
        assert mock_uvicorn.called


def test_analytics_and_cost_edge_cases():
    traj_empty = Trajectory(input_prompt="empty", steps=[])
    cost = calculate_trajectory_cost(traj_empty, default_model="ollama")
    assert cost.total_cost_usd == 0.0

    latency = calculate_latency_breakdown(traj_empty)
    assert latency.total_duration_ms == 0.0


def test_visualizations_empty_cases():
    assert "No trajectory steps" in render_ascii_waterfall(Trajectory(steps=[]))
    assert "<svg" in render_svg_waterfall(Trajectory(steps=[]))
