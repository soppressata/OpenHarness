"""
CLI Tooling ('lasb') for N-Dimensional Isolated Sandbox Meshing (AC5).
Provides administrative commands for universe orchestration, zero-trust meshing,
God Mode GraphQL queries, dashboard serving, and onboarding.
"""

import sys
import os
import argparse
import json
import time
from typing import List, Optional

from .orchestrator import UniverseOrchestrator, UniverseStatus, ComputeQuota
from .rust_orchestrator import RustOrchestratorBridge
from .mesh import MeshNetworkManager, TrustAction
from .graphql_api import GodModeGraphQLAPI
from .dashboard import DashboardServer
from .onboarding import OnboardingWizard
from .pipeline_generator import AIPipelineGenerator
from .self_healing import SelfHealingEngine
from .diagnostics import DiagnosisReport

# Shared global singleton orchestrator instance for CLI daemon mode
_global_orchestrator = UniverseOrchestrator()
_global_mesh = MeshNetworkManager()
_global_graphql = GodModeGraphQLAPI(_global_orchestrator, _global_mesh)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lasb",
        description="LocalAgentSandbox CLI - The Multi-Verse Agent Ecology",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Onboarding command group
    onboard_p = subparsers.add_parser("onboard", help="Run guided onboarding and setup wizard")
    onboard_p.add_argument("--interactive", action="store_true", help="Run interactive prompts")
    onboard_p.add_argument("--name-prefix", type=str, default="agent-node", help="Default sandbox name prefix")
    onboard_p.add_argument("--memory", type=int, default=512, help="Default memory quota per sandbox in MB")
    onboard_p.add_argument("--port", type=int, default=8080, help="Default dashboard port")
    onboard_p.add_argument("--no-sandbox", action="store_true", help="Skip creating initial sandbox")

    init_p = subparsers.add_parser("init", help="Alias for onboard command")
    init_p.add_argument("--interactive", action="store_true", help="Run interactive prompts")
    init_p.add_argument("--name-prefix", type=str, default="agent-node", help="Default sandbox name prefix")
    init_p.add_argument("--memory", type=int, default=512, help="Default memory quota per sandbox in MB")
    init_p.add_argument("--port", type=int, default=8080, help="Default dashboard port")
    init_p.add_argument("--no-sandbox", action="store_true", help="Skip creating initial sandbox")

    # Self-Healing & Remediation command group
    heal_parser = subparsers.add_parser("self-heal", help="Generate code patch, verify in isolated sandbox, and format diff for review")
    heal_parser.add_argument("--target-file", type=str, required=True, help="Target file path requiring repair")
    heal_parser.add_argument("--error-type", type=str, default="ZeroDivisionError", help="Error type string")
    heal_parser.add_argument("--root-cause", type=str, default="Division by zero encountered", help="Root cause explanation")
    heal_parser.add_argument("--suggested-fix", type=str, default="Add zero-check guardrail", help="Suggested fix description")
    heal_parser.add_argument("--original-code-file", type=str, default=None, help="File path containing original code")
    heal_parser.add_argument("--provider", type=str, default="google", choices=["google", "openai", "anthropic"], help="LLM Provider adapter")
    heal_parser.add_argument("--model", type=str, default=None, help="LLM model name")
    heal_parser.add_argument("--api-key", type=str, default=None, help="API key for LLM provider")
    heal_parser.add_argument("--json", action="store_true", help="Output remediation report in JSON format")
    heal_parser.add_argument("-o", "--output", type=str, help="File path to save the remediation report")

    # AI Pipeline Generation command group
    gen_parser = subparsers.add_parser("ai-generate", help="Generate AI deployment pipeline execution plan and architecture docs")
    gen_parser.add_argument("prompt", type=str, nargs="?", default="", help="Natural language prompt describing desired deployment state")
    gen_parser.add_argument("-p", "--prompt", dest="prompt_flag", type=str, help="Alternative flag for natural language prompt")
    gen_parser.add_argument("--provider", type=str, default="google", choices=["google", "openai", "anthropic"], help="LLM Provider adapter")
    gen_parser.add_argument("--model", type=str, default=None, help="LLM model name")
    gen_parser.add_argument("--api-key", type=str, default=None, help="API key for LLM provider")
    gen_parser.add_argument("--json", action="store_true", help="Output execution plan and architecture docs in JSON format")
    gen_parser.add_argument("-o", "--output", type=str, help="File path to save the generated execution plan")

    # Universe command group
    uv_parser = subparsers.add_parser("universe", help="Universe sandbox management")
    uv_sub = uv_parser.add_subparsers(dest="action", help="Universe action")

    # universe create
    create_p = uv_sub.add_parser("create", help="Create agent universe sandbox(es)")
    create_p.add_argument("--count", type=int, default=1, help="Number of sandboxes to create (e.g. 1000)")
    create_p.add_argument("--name-prefix", type=str, default="agent-node", help="Name prefix for sandboxes")
    create_p.add_argument("--memory", type=int, default=512, help="Memory quota per sandbox in MB")
    create_p.add_argument("--use-rust", action="store_true", help="Use Rust core orchestrator bridge")

    # universe list
    list_p = uv_sub.add_parser("list", help="List running sandboxes")
    list_p.add_argument("--status", type=str, choices=["RUNNING", "PAUSED", "STOPPED", "MESHED"], help="Filter status")
    list_p.add_argument("--limit", type=int, default=50, help="Max items to list")
    list_p.add_argument("--json", action="store_true", help="Output raw JSON")

    # universe get
    get_p = uv_sub.add_parser("get", help="Get universe details")
    get_p.add_argument("universe_id", type=str, help="Universe ID")

    # universe status
    status_p = uv_sub.add_parser("status", help="Get universe status and health details")
    status_p.add_argument("universe_id", type=str, help="Universe ID")

    # universe start
    start_p = uv_sub.add_parser("start", help="Start universe sandbox")
    start_p.add_argument("universe_id", type=str, help="Universe ID")

    # universe stop
    stop_p = uv_sub.add_parser("stop", help="Stop universe sandbox")
    stop_p.add_argument("universe_id", type=str, help="Universe ID")

    # universe destroy
    dest_p = uv_sub.add_parser("destroy", help="Destroy universe")
    dest_p.add_argument("universe_id", type=str, help="Universe ID")

    # Mesh command group
    mesh_parser = subparsers.add_parser("mesh", help="Zero-trust mesh network management")
    mesh_sub = mesh_parser.add_subparsers(dest="action", help="Mesh action")

    # mesh connect
    conn_p = mesh_sub.add_parser("connect", help="Connect two sandboxes over zero-trust mesh")
    conn_p.add_argument("source_id", type=str, help="Source Universe ID")
    conn_p.add_argument("target_id", type=str, help="Target Universe ID")

    # mesh topology
    top_p = mesh_sub.add_parser("topology", help="View mesh network topology")

    # Godmode command group
    gm_parser = subparsers.add_parser("godmode", help="God Mode GraphQL Observability")
    gm_sub = gm_parser.add_subparsers(dest="action", help="Godmode action")
    query_p = gm_sub.add_parser("query", help="Execute GraphQL query")
    query_p.add_argument("query_str", type=str, help="GraphQL query string")

    # Dashboard command group
    dash_parser = subparsers.add_parser("dashboard", help="Start web visualization dashboard")
    dash_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address")
    dash_parser.add_argument("--port", type=int, default=8080, help="Port number")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.subcommand:
        parser.print_help()
        print("\nTip: Run 'lasb onboard' or 'lasb init' for guided quickstart setup.")
        return 0

    if parsed.subcommand in ("onboard", "init"):
        wizard = OnboardingWizard()
        wizard.execute_onboarding(
            interactive=getattr(parsed, "interactive", False),
            name_prefix=getattr(parsed, "name_prefix", "agent-node"),
            memory_mb=getattr(parsed, "memory", 512),
            dashboard_port=getattr(parsed, "port", 8080),
            create_initial_sandbox=not getattr(parsed, "no_sandbox", False),
            orchestrator=_global_orchestrator,
            verbose=True,
        )
        return 0

    if parsed.subcommand == "universe":
        if parsed.action == "create":
            t0 = time.time()
            if getattr(parsed, "use_rust", False):
                bridge = RustOrchestratorBridge(use_rust=True, orchestrator=_global_orchestrator)
                nodes = bridge.batch_create(count=parsed.count, name_prefix=parsed.name_prefix)
                elapsed = time.time() - t0
                print(f"Successfully launched {len(nodes)} sandboxes using Rust bridge in {elapsed:.4f} seconds!")
                if nodes:
                    print(f"Sample Sandbox ID: {nodes[0].id} .. {nodes[-1].id}")
            elif parsed.count == 1:
                quota = ComputeQuota(memory_mb=parsed.memory)
                uv = _global_orchestrator.create_universe(name=f"{parsed.name_prefix}-0", quota=quota)
                print(f"Created universe: {uv.id} ({uv.name}) [Status: {uv.status.value if isinstance(uv.status, UniverseStatus) else uv.status}]")
            else:
                quota = ComputeQuota(memory_mb=parsed.memory)
                nodes = _global_orchestrator.create_universes_batch(count=parsed.count, name_prefix=parsed.name_prefix, template_quota=quota)
                elapsed = time.time() - t0
                print(f"Successfully launched {len(nodes)} sandboxes in {elapsed:.4f} seconds!")
                print(f"Sample Sandbox ID: {nodes[0].id} .. {nodes[-1].id}")

        elif parsed.action == "list":
            st = UniverseStatus(parsed.status) if parsed.status else None
            items = _global_orchestrator.list_universes(status=st, limit=parsed.limit)
            if getattr(parsed, "json", False):
                print(json.dumps([u.to_dict() for u in items], indent=2))
            else:
                print(f"{'UNIVERSE ID':<15} {'NAME':<25} {'STATUS':<12} {'VIRTUAL IP':<16}")
                print("-" * 70)
                for u in items:
                    st_val = u.status.value if isinstance(u.status, UniverseStatus) else str(u.status)
                    print(f"{u.id:<15} {u.name:<25} {st_val:<12} {u.network.virtual_ip:<16}")

        elif parsed.action in ("status", "get"):
            uv = _global_orchestrator.get_universe(parsed.universe_id)
            if uv:
                info = uv.to_dict()
                info["health"] = uv.health_check()
                print(json.dumps(info, indent=2))
            else:
                print(f"Error: Universe '{parsed.universe_id}' not found.", file=sys.stderr)
                return 1

        elif parsed.action == "start":
            success = _global_orchestrator.start_universe(parsed.universe_id)
            if success:
                print(f"Started universe '{parsed.universe_id}'.")
            else:
                print(f"Error: Universe '{parsed.universe_id}' not found.", file=sys.stderr)
                return 1

        elif parsed.action == "stop":
            success = _global_orchestrator.stop_universe(parsed.universe_id)
            if success:
                print(f"Stopped universe '{parsed.universe_id}'.")
            else:
                print(f"Error: Universe '{parsed.universe_id}' not found.", file=sys.stderr)
                return 1

        elif parsed.action == "destroy":
            success = _global_orchestrator.destroy_universe(parsed.universe_id)
            if success:
                print(f"Destroyed universe '{parsed.universe_id}'.")
            else:
                print(f"Error: Universe '{parsed.universe_id}' not found.", file=sys.stderr)
                return 1

    elif parsed.subcommand == "mesh":
        if parsed.action == "connect":
            src = _global_orchestrator.get_universe(parsed.source_id)
            tgt = _global_orchestrator.get_universe(parsed.target_id)
            if not src or not tgt:
                print("Error: Source or target universe not found.", file=sys.stderr)
                return 1
            chan = _global_mesh.negotiate_channel(src, tgt)
            if chan and chan.is_active:
                print(f"Successfully established mTLS channel: {chan.channel_id}")
            else:
                print("Failed to establish mesh connection.", file=sys.stderr)
                return 1

        elif parsed.action == "topology":
            topo = _global_mesh.get_mesh_topology()
            print(json.dumps(topo, indent=2))

    elif parsed.subcommand == "godmode":
        if parsed.action == "query":
            res = _global_graphql.execute(parsed.query_str)
            print(json.dumps(res, indent=2))

    elif parsed.subcommand == "self-heal":
        target_file = parsed.target_file
        orig_code = ""
        if getattr(parsed, "original_code_file", None) and os.path.exists(parsed.original_code_file):
            with open(parsed.original_code_file, "r", encoding="utf-8") as f:
                orig_code = f.read()
        else:
            orig_code = "def process_data(val, div):\n    return val / div\n"

        diagnosis = DiagnosisReport(
            step_id="step-cli-repair",
            step_name="CLI Repair Task",
            error_type=parsed.error_type,
            root_cause=parsed.root_cause,
            summary=f"CLI failure trigger: {parsed.error_type}",
            suggested_fix=parsed.suggested_fix,
            confidence_score=0.9,
            provider=parsed.provider,
        )

        engine = SelfHealingEngine(
            provider=getattr(parsed, "provider", "google"),
            api_key=getattr(parsed, "api_key", None),
            model=getattr(parsed, "model", None),
            orchestrator=_global_orchestrator,
        )

        report = engine.remediate_failure(
            diagnosis=diagnosis,
            target_file=target_file,
            original_code=orig_code,
        )

        if getattr(parsed, "json", False):
            output_str = json.dumps(report.to_dict(), indent=2)
        else:
            output_str = report.format_review_text()

        output_path = getattr(parsed, "output", None)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(output_str)
            print(f"Self-healing remediation report saved to {output_path}")
        else:
            print(output_str)
        return 0

    elif parsed.subcommand == "ai-generate":
        prompt = getattr(parsed, "prompt", None) or getattr(parsed, "prompt_flag", None)
        if not prompt:
            print("Error: A natural language prompt is required.", file=sys.stderr)
            return 1
        generator = AIPipelineGenerator(
            provider=getattr(parsed, "provider", "google"),
            api_key=getattr(parsed, "api_key", None),
            model=getattr(parsed, "model", None),
        )
        result = generator.generate_pipeline(prompt)
        if getattr(parsed, "json", False):
            output_str = json.dumps(result.to_dict(), indent=2)
        else:
            output_str = result.format_text()

        output_path = getattr(parsed, "output", None)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(output_str)
            print(f"Pipeline generation plan saved to {output_path}")
        else:
            print(output_str)
        return 0

    elif parsed.subcommand == "dashboard":
        server = DashboardServer(
            orchestrator=_global_orchestrator,
            mesh_manager=_global_mesh,
            host=parsed.host,
            port=parsed.port,
        )
        print(f"Starting Multi-Verse Agent Ecology Visualization Dashboard at http://{parsed.host}:{parsed.port}")
        server.start_blocking()

    return 0


if __name__ == "__main__":
    sys.exit(main())


"""
Cli module for OpenHarness.
Provides core functionality for the cli subsystem.
"""
import sys
import json
import click
from typing import List, Optional
from local_agent_sandbox.core import LocalAgentSandbox, SandboxConfig
from local_agent_sandbox.pipeline_generator import AIPipelineGenerator


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """LocalAgentSandbox CLI - Sub-10ms Local Process Isolation for AI Coding Agents."""
    pass


@cli.command()
@click.argument("command")
@click.option("--timeout", default=30.0, help="Maximum execution timeout in seconds.")
@click.option("--dir", default=None, help="Custom sandbox directory path.")
def run(command: str, timeout: float, dir: str):
    """Run a bash command inside isolated local sandbox."""
    config = SandboxConfig(max_timeout_seconds=timeout)
    sandbox = LocalAgentSandbox(config=config, sandbox_dir=dir)
    
    click.echo(f"⚡ Executing inside sandbox: '{command}'")
    result = sandbox.execute(command)

    if result.blocked:
        click.secho(f"❌ BLOCKED: {result.stderr}", fg="red", bold=True)
    else:
        color = "green" if result.exit_code == 0 else "red"
        click.secho(f"Exit Code: {result.exit_code} ({result.duration_ms:.1f}ms)", fg=color, bold=True)
        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.secho(result.stderr, fg="yellow")

    sandbox.cleanup()


@cli.command("ai-generate")
@click.argument("prompt_pos", required=False, default=None, metavar="PROMPT")
@click.option("-p", "--prompt", "prompt_opt", default=None, help="Natural language prompt for pipeline generation.")
@click.option("--provider", default="google", help="AI provider (e.g., google, openai, anthropic).")
@click.option("--json", "output_json", is_flag=True, help="Output execution plan and architecture docs in JSON format.")
@click.option("-o", "--output", default=None, help="File path to save the output.")
def ai_generate(
    prompt_pos: Optional[str],
    prompt_opt: Optional[str],
    provider: str,
    output_json: bool,
    output: Optional[str]
):
    """Generate an AI pipeline execution plan and architecture docs from a prompt."""
    prompt = prompt_pos or prompt_opt
    if not prompt:
        sys.stderr.write("Error: A natural language prompt is required\n")
        raise SystemExit(1)

    generator = AIPipelineGenerator(provider=provider)
    result = generator.generate_pipeline(prompt)

    if output_json:
        json_output = result.model_dump_json(indent=2)
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(json_output)
        click.echo(json_output)
    else:
        out_lines = [
            "=== OpenHarness AI Pipeline Execution Plan ===",
            f"Pipeline ID: {result.pipeline_id}",
            f"Target State: {result.target_state}",
            f"Provider: {result.provider}",
            f"SLA Target: {result.execution_plan.sla_target}",
            f"Cost Limit: {result.execution_plan.cost_limit}",
            "",
            "Execution Steps:",
        ]
        for step in result.execution_plan.steps:
            out_lines.append(f"  {step.id}. {step.name}: {step.action}")
        out_lines.extend([
            "",
            "=== Foundational Architecture Documentation ===",
            f"Topology: {result.architecture_documentation.topology}",
            f"Resilience: {result.architecture_documentation.resilience}",
            f"Cost Optimization: {result.architecture_documentation.cost_optimization}",
            f"Security Baseline: {result.architecture_documentation.security_baseline}",
        ])
        formatted_output = "\n".join(out_lines)
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(formatted_output)
        click.echo(formatted_output)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint function that accepts list of arguments and returns status code."""
    if args is None:
        args = sys.argv[1:]
    
    try:
        cli(args=args, standalone_mode=False)
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except click.ClickException as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
