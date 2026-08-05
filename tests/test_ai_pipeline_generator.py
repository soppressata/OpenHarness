"""
Unit tests for AI Pipeline Generator CLI ('ai-generate') and Engine.
"""

import json
from local_agent_sandbox.cli import main as cli_main
from local_agent_sandbox.pipeline_generator import AIPipelineGenerator, AIPipelineResult


def test_pipeline_generator_direct():
    generator = AIPipelineGenerator(provider="google")
    prompt = "Deploy microservice X to AWS with 99.99% uptime, keeping costs under $500/mo"
    result = generator.generate_pipeline(prompt)

    assert isinstance(result, AIPipelineResult)
    assert result.target_state == prompt
    assert result.execution_plan.sla_target == "99.99% uptime"
    assert result.execution_plan.cost_limit == "$500/mo"
    assert len(result.execution_plan.steps) == 5

    arch = result.architecture_documentation
    assert "Compute Layer" in arch.topology
    assert "SLA Target" in arch.resilience
    assert "Budget Limit" in arch.cost_optimization
    assert "Zero-Trust Mesh" in arch.security_baseline


def test_cli_ai_generate_text_output(capsys):
    ret = cli_main(["ai-generate", "Deploy microservice billing to AWS with 99.9% uptime, keeping costs under $200/mo"])
    assert ret == 0

    captured = capsys.readouterr()
    assert "OpenHarness AI Pipeline Execution Plan" in captured.out
    assert "Pipeline ID:" in captured.out
    assert "Deploy microservice billing to AWS" in captured.out
    assert "Foundational Architecture Documentation" in captured.out


def test_cli_ai_generate_json_output(capsys):
    ret = cli_main(["ai-generate", "--prompt", "Deploy auth service to GCP", "--json"])
    assert ret == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["target_state"] == "Deploy auth service to GCP"
    assert "execution_plan" in data
    assert "architecture_documentation" in data
    assert len(data["execution_plan"]["steps"]) > 0


def test_cli_ai_generate_output_file(tmp_path):
    out_file = tmp_path / "pipeline_plan.json"
    ret = cli_main(["ai-generate", "Deploy search worker to Azure", "--json", "-o", str(out_file)])
    assert ret == 0

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    data = json.loads(content)
    assert data["target_state"] == "Deploy search worker to Azure"
    assert "execution_plan" in data


def test_cli_ai_generate_missing_prompt(capsys):
    ret = cli_main(["ai-generate"])
    assert ret == 1

    captured = capsys.readouterr()
    assert "Error: A natural language prompt is required" in captured.err


def test_cli_ai_generate_with_provider_and_flag(capsys):
    ret = cli_main(["ai-generate", "-p", "Deploy payment service to AWS", "--provider", "openai", "--json"])
    assert ret == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["target_state"] == "Deploy payment service to AWS"
    assert "openai" in data["provider"]
