"""
Main module for OpenHarness.
Provides core functionality for the main subsystem.
"""
import os
import sys
from typing import Optional, Tuple
import click
from openharness.core.storage import StorageEngine
from openharness.core.exporters import export_to_json, export_to_html, export_to_junit_xml
from openharness.core.visualizations import render_ascii_waterfall, render_ascii_scorecard, render_ascii_quality_radar
from openharness.core.synthetic import generate_synthetic_dataset
from openharness.ci_generator import generate_github_actions_yaml
from local_agent_sandbox.fleet import (
    handle_fleet_dashboard,
    handle_fleet_init,
    handle_fleet_join,
    handle_fleet_migrate,
    handle_fleet_run,
    handle_fleet_status,
)


@click.group()
@click.version_option(version="0.1.0", message="OpenHarness Agentic Evaluator v%(version)s")
def cli():
    """OpenHarness CLI - Zero-Cost, Local-First Agentic Harness Evaluator."""
    pass


@cli.group()
def fleet():
    """Manage and run tests on a HarnessFleet grid."""
    pass


@fleet.command("init")
@click.option("--cluster-name", default="harness-fleet-primary", show_default=True)
@click.option("--output", "output_path", default="fleet.yaml", show_default=True)
def fleet_init(cluster_name: str, output_path: str) -> None:
    """Generate a fleet.yaml configuration file."""
    handle_fleet_init(cluster_name=cluster_name, output_path=output_path)


@fleet.command("join")
@click.option("--conductor", "conductor_address", default="127.0.0.1:9443", show_default=True)
@click.option("--token", default=None, help="Short-lived worker enrollment token.")
def fleet_join(conductor_address: str, token: Optional[str]) -> None:
    """Enroll the current host as a Fleet worker."""
    handle_fleet_join(conductor_address=conductor_address, token=token)


@fleet.command("run")
@click.argument("test_files", nargs=-1, type=click.Path(exists=True, dir_okay=False))
@click.option("--shards", default="auto", show_default=True, help="Shard count or auto.")
@click.option("--nodes", "nodes_count", default=4, show_default=True, type=click.IntRange(min=1))
@click.option("--timeout", default=300, show_default=True, type=click.IntRange(min=1))
@click.option("--resume", is_flag=True, help="Resume from the last fleet checkpoint.")
@click.option("--config", "config_path", default="fleet.yaml", show_default=True)
def fleet_run(
    test_files: Tuple[str, ...],
    shards: str,
    nodes_count: int,
    timeout: int,
    resume: bool,
    config_path: str,
) -> None:
    """Run test files across the Fleet grid."""
    exit_code = handle_fleet_run(
        test_files=list(test_files) or None,
        shards=shards,
        nodes_count=nodes_count,
        timeout=timeout,
        resume=resume,
        config_path=config_path,
    )
    if exit_code:
        raise click.exceptions.Exit(exit_code)


@fleet.command("status")
def fleet_status() -> None:
    """Display the current Fleet node health table."""
    handle_fleet_status()


@fleet.command("dashboard")
def fleet_dashboard() -> None:
    """Display a snapshot of Fleet telemetry and failure clusters."""
    handle_fleet_dashboard()


@fleet.command("migrate")
@click.option("--source", "source_file", default=None, type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "output_path", default="fleet.yaml", show_default=True)
def fleet_migrate(source_file: Optional[str], output_path: str) -> None:
    """Migrate an existing OpenHarness configuration to fleet.yaml."""
    handle_fleet_migrate(source_file=source_file, output_path=output_path)


@cli.command()
@click.option("--db", default=".openharness/evals.db", help="Path to SQLite evals database.")
def report(db):
    """View evaluation summary report in terminal."""
    storage = StorageEngine(db_path=db)
    runs = storage.get_runs(limit=10)

    if not runs:
        click.echo("No evaluation runs found in " + db)
        return

    click.echo("\n" + "=" * 65)
    click.echo("       OPENHARNESS EVALUATION SUMMARY REPORT       ")
    click.echo("=" * 65)

    for run in runs:
        passed = run["passed_count"]
        total = run["total_count"]
        pass_rate = (passed / total * 100.0) if total > 0 else 0.0
        status_color = "green" if pass_rate == 100.0 else ("yellow" if pass_rate >= 50.0 else "red")
        
        click.secho(
            f"Run ID: {run['id']} | Name: {run['name']} | Pass Rate: {pass_rate:.1f}% ({passed}/{total}) | Duration: {run['duration_ms']:.1f}ms",
            fg=status_color,
            bold=True
        )

        run_detail = storage.get_run_details(run["id"])
        if run_detail:
            for res in run_detail.get("results", []):
                symbol = "✅" if res["passed"] else "❌"
                click.echo(f"  {symbol} Case: {res['test_case_name']} (Score: {res['total_score']:.2f}, {res['duration_ms']:.1f}ms)")
                for m in res.get("metrics", []):
                    m_symbol = "  └─ ✔" if m["passed"] else "  └─ ✖"
                    click.echo(f"    {m_symbol} [{m['category']}] {m['name']}: {m['reason']}")
        click.echo("-" * 65)


@cli.command()
@click.option("--run-id", help="Run ID to render ASCII visualization for (defaults to latest run).")
@click.option("--db", default=".openharness/evals.db", help="Path to SQLite evals database.")
def viz(run_id, db):
    """Render terminal ASCII Waterfall & Scorecard visualizations."""
    storage = StorageEngine(db_path=db)
    
    if not run_id:
        runs = storage.get_runs(limit=1)
        if not runs:
            click.echo("No evaluation runs found in " + db)
            return
        run_id = runs[0]["id"]

    details = storage.get_run_details(run_id)
    if not details:
        click.secho(f"Error: Run ID '{run_id}' not found.", fg="red")
        sys.exit(1)

    click.echo("\n" + "=" * 65)
    click.echo(f"📊 VISUALIZATIONS FOR RUN: {details['name']} ({run_id})")
    click.echo("=" * 65)

    # Render Scorecard & Quality Matrix
    from openharness.core.types import EvaluationResult
    results = [EvaluationResult(**r) for r in details.get("results", [])]
    click.echo(render_ascii_scorecard(results))
    click.echo("\n" + render_ascii_quality_radar(results))

    # Render Waterfalls for trajectories
    for res in details.get("results", []):
        click.secho(f"\n▶ Test Case: {res['test_case_name']}", fg="cyan", bold=True)
        if res.get("trajectory"):
            from openharness.core.types import Trajectory
            traj = Trajectory(**res["trajectory"])
            click.echo(render_ascii_waterfall(traj))


@cli.command()
@click.option("--prompt", required=True, help="Seed prompt or domain description.")
@click.option("--n-cases", default=5, help="Number of synthetic test cases to generate.")
@click.option("--out", required=True, help="Output JSONL file path.")
@click.option("--model", default="ollama/llama3.1", help="LLM model spec for generation.")
def synthetic(prompt, n_cases, out, model):
    """Generate a synthetic evaluation dataset using local or cloud LLMs."""
    click.secho(f"🤖 Generating {n_cases} synthetic test cases using model '{model}'...", fg="cyan")
    dataset = generate_synthetic_dataset(seed_prompt=prompt, n_cases=n_cases, model=model)
    dataset.to_jsonl(out)
    click.secho(f"✅ Generated synthetic dataset with {len(dataset.cases)} cases saved to {out}", fg="green")


@cli.command()
@click.option("--run-id", required=True, help="Evaluation run ID to export.")
@click.option("--format", type=click.Choice(["json", "html", "junit"]), default="json", help="Export format.")
@click.option("--out", help="Output file path (prints to stdout if omitted).")
@click.option("--db", default=".openharness/evals.db", help="Path to SQLite evals database.")
def export(run_id, format, out, db):
    """Export evaluation run report to JSON, HTML, or JUnit XML."""
    storage = StorageEngine(db_path=db)
    details = storage.get_run_details(run_id)
    if not details:
        click.secho(f"Error: Run ID '{run_id}' not found.", fg="red")
        sys.exit(1)

    if format == "json":
        output_content = export_to_json(details)
    elif format == "html":
        output_content = export_to_html(details)
    elif format == "junit":
        output_content = export_to_junit_xml(details)

    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(output_content)
        click.secho(f"Exported run '{run_id}' ({format}) to {out}", fg="green")
    else:
        click.echo(output_content)


@cli.command()
@click.option("--port", default=8501, help="Port to run the UI server on.")
@click.option("--host", default="127.0.0.1", help="Host address for the UI server.")
@click.option("--db", default=".openharness/evals.db", help="Path to SQLite evals database.")
def ui(port, host, db):
    """Launch the embedded local web dashboard (`harness ui`)."""
    try:
        import uvicorn
        from openharness.server.app import create_app

        os.environ["OPENHARNESS_DB"] = db
        app = create_app(db_path=db)
        
        click.secho(f"\n🚀 Launching OpenHarness Dashboard at http://{host}:{port}", fg="cyan", bold=True)
        click.secho(f"   Using Database: {db}\n", fg="bright_black")
        uvicorn.run(app, host=host, port=port, log_level="info")
    except ImportError as e:
        click.secho(f"Error starting dashboard UI: {str(e)}. Ensure fastapi and uvicorn are installed.", fg="red")


@cli.command()
@click.option("--ci", type=click.Choice(["github"]), help="CI provider to scaffold a workflow template for.")
def init(ci):
    """Initialize a sample test file, or scaffold a CI workflow template."""
    sample_content = '''from openharness import eval_case, assert_tool_called, assert_exact_match, eval_goal_completion

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
'''
    target_path = "harness_example.py"
    if not os.path.exists(target_path):
        with open(target_path, "w") as f:
            f.write(sample_content)
        click.secho(f"Created sample evaluation file: {target_path}", fg="green")
        click.echo("Run it with: python3 harness_example.py")
        click.echo("View reports with: harness report")
        click.echo("Launch dashboard with: harness ui")
    else:
        click.echo(f"File {target_path} already exists.")

    env_path = ".env.example"
    env_content = """# OpenHarness Configuration Environment Variables

# 1. LLM API Keys and Endpoints (for LLM-as-a-Judge and Synthetic Dataset Generation)
# If using OpenAI:
# OPENAI_API_KEY=your-openai-api-key-here
# If using an OpenAI-compatible provider (e.g. OpenRouter, DeepSeek, Local vLLM):
# OPENAI_BASE_URL=https://api.openai.com/v1

# 2. Database Configuration
# Defaults to local SQLite at `.openharness/evals.db`.
# To use a shared PostgreSQL instance, uncomment and set the connection string:
# OPENHARNESS_DB_URL=postgresql://username:password@localhost:5432/openharness_db
"""
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write(env_content)
        click.secho(f"Created configuration template: {env_path}", fg="green")
    else:
        click.echo(f"File {env_path} already exists.")

    if ci:
        path = ".github/workflows/eval.yml"
        written = generate_github_actions_yaml(path)
        if written:
            click.secho("Scaffolded github CI workflow template to .github/workflows/eval.yml", fg="green")
            click.echo("Commit it and push to run OpenHarness evals in GitHub Actions.")
        else:
            click.echo(f"File {path} already exists.")


def main():
    cli()


if __name__ == "__main__":
    main()


def replay_batch(run_id):
    print(f"Replaying run {run_id}...")
    return True
