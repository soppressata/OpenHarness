import json
from click.testing import CliRunner
from openharness.cli.main import cli
from openharness import Harness, assert_exact_match


def test_cli_report_empty(tmp_path):
    runner = CliRunner()
    db_file = str(tmp_path / "non_existent.db")
    result = runner.invoke(cli, ["report", "--db", db_file])
    assert result.exit_code == 0
    assert "No evaluation runs found" in result.output


def test_cli_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "harness_example.py").exists()


def test_cli_viz_command(tmp_path):
    db_file = str(tmp_path / "viz.db")
    h = Harness(name="Viz Run", db_path=db_file)
    h.run_case("Case 1", lambda x: "hello", "hi", [assert_exact_match("hello")])
    run_id = h.save()

    runner = CliRunner()
    result = runner.invoke(cli, ["viz", "--run-id", run_id, "--db", db_file])
    assert result.exit_code == 0
    assert "VISUALIZATIONS FOR RUN" in result.output

    # Invalid run_id viz
    res_err = runner.invoke(cli, ["viz", "--run-id", "invalid_id", "--db", db_file])
    assert res_err.exit_code != 0


import os
import pytest
from click.testing import CliRunner
from local_agent_sandbox.cli import cli, generate_ci_template


def test_cli_run_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "echo 'CLI test'"])
    assert result.exit_code == 0
    assert "CLI test" in result.output


def test_cli_blocked_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "rm -rf /"])
    assert "BLOCKED" in result.output


def test_cli_init_github():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "--ci", "github"])
        assert result.exit_code == 0
        assert "Scaffolded github CI workflow template" in result.output
        eval_yml_path = os.path.join(".github", "workflows", "eval.yml")
        assert os.path.exists(eval_yml_path)
        with open(eval_yml_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "actions/cache" in content
        assert "actions/upload-artifact" in content
        assert "report.html" in content


def test_generate_ci_template_invalid():
    with pytest.raises(ValueError, match="Unsupported CI provider"):
        generate_ci_template("unsupported_provider")
