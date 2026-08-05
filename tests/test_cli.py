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
