"""
Tests for AI Pipeline Generation CLI and generator module.
"""

import json
import pytest
from click.testing import CliRunner
from local_agent_sandbox.cli import cli, main as cli_main
from local_agent_sandbox.pipeline_generator import AIPipelineGenerator, PipelinePlan


def test_import_main_alias():
    """Verify cli module exports main as an alias for cli."""
    assert cli_main is cli


def test_generator_direct_invocation():
    """Test AIPipelineGenerator directly."""
    generator = AIPipelineGenerator()
    prompt = "Deploy microservice X to AWS with 99.99% uptime, keeping costs under $500/mo"
    plan = generator.generate(prompt)

    assert isinstance(plan, PipelinePlan)
    assert plan.prompt == prompt
    assert "AWS" in plan.target_environment
    assert len(plan.stages) >= 3
    assert plan.architecture_doc.title is not None
    assert "99.99% uptime" in str(plan.architecture_doc.constraints)
    assert "$500/month" in str(plan.architecture_doc.constraints)


def test_cli_ai_generate_positional_argument():
    """Test ai-generate CLI command with positional prompt argument."""
    runner = CliRunner()
    result = runner.invoke(cli_main, ["ai-generate", "Deploy microservice X to AWS"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["prompt"] == "Deploy microservice X to AWS"
    assert "stages" in data
    assert "architecture_doc" in data


def test_cli_ai_generate_option():
    """Test ai-generate CLI command with --prompt option."""
    runner = CliRunner()
    result = runner.invoke(cli_main, ["ai-generate", "--prompt", "Deploy to GCP with Docker"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["prompt"] == "Deploy to GCP with Docker"
    assert "GCP" in data["target_environment"]


def test_cli_ai_generate_output_file(tmp_path):
    """Test ai-generate CLI command with output file parameter."""
    runner = CliRunner()
    output_file = tmp_path / "plan.json"
    result = runner.invoke(cli_main, [
        "ai-generate",
        "Deploy to Kubernetes cluster",
        "--output", str(output_file)
    ])

    assert result.exit_code == 0
    assert output_file.exists()
    file_content = json.loads(output_file.read_text())
    assert file_content["prompt"] == "Deploy to Kubernetes cluster"
    assert "Kubernetes" in file_content["target_environment"]


def test_cli_ai_generate_missing_prompt():
    """Test ai-generate CLI command with missing prompt."""
    runner = CliRunner()
    result = runner.invoke(cli_main, ["ai-generate"])

    assert result.exit_code != 0
    assert "Missing prompt" in result.output or "Error" in result.output
