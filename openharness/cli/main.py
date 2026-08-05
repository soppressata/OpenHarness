import os
import sys
import click
from openharness.core.storage import StorageEngine
from openharness.core.exporters import export_to_json, export_to_html, export_to_junit_xml
from openharness.core.visualizations import render_ascii_waterfall, render_ascii_scorecard
from openharness.core.synthetic import generate_synthetic_dataset


@click.group()
@click.version_option(version="0.1.0", message="OpenHarness Agentic Evaluator v%(version)s")
def cli():
    """OpenHarness CLI - Zero-Cost, Local-First Agentic Harness Evaluator."""
    pass


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

    # Render Scorecard
    from openharness.core.types import EvaluationResult
    results = [EvaluationResult(**r) for r in details.get("results", [])]
    click.echo(render_ascii_scorecard(results))

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
def init():
    """Initialize sample harness test file in current directory."""
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


def main():
    cli()


if __name__ == "__main__":
    main()
