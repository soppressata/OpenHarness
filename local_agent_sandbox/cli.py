"""
CLI Tooling for LocalAgentSandbox & OpenHarness.
Provides administrative commands including 'ai-generate' for AI deployment pipeline generation.
"""

import sys
import os
import argparse
import json
import time
from typing import List, Optional

from .pipeline_generator import AIPipelineGenerator
from .diagnostics import DiagnosisReport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lasb",
        description="LocalAgentSandbox CLI - AI Pipeline & Harness Tooling",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Onboarding / init command group
    onboard_p = subparsers.add_parser("onboard", help="Run guided onboarding and setup wizard")
    onboard_p.add_argument("--interactive", action="store_true", help="Run interactive prompts")

    init_p = subparsers.add_parser("init", help="Alias for onboard command")
    init_p.add_argument("--interactive", action="store_true", help="Run interactive prompts")

    # Self-Healing command group
    heal_parser = subparsers.add_parser("self-heal", help="Generate code patch and remediation report")
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

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """
    Main CLI entry point for local_agent_sandbox.
    """
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.subcommand:
        parser.print_help()
        return 0

    if parsed.subcommand in ("onboard", "init"):
        print("Running onboarding wizard...")
        return 0

    if parsed.subcommand == "ai-generate":
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

    return 0


if __name__ == "__main__":
    sys.exit(main())


# AI Pipeline Generation command group
    gen_parser = subparsers.add_parser("ai-generate", help="Generate AI deployment pipeline execution plan and architecture docs")
    gen_parser.add_argument("prompt", type=str, nargs="?", default="", help="Natural language prompt describing desired deployment state")
    gen_parser.add_argument("-p", "--prompt", dest="prompt_flag", type=str, help="Alternative flag for natural language prompt")
    gen_parser.add_argument("--provider", type=str, default="google", choices=["google", "openai", "anthropic"], help="LLM Provider adapter")
    gen_parser.add_argument("--model", type=str, default=None, help="LLM model name")
    gen_parser.add_argument("--api-key", type=str, default=None, help="API key for LLM provider")
    gen_parser.add_argument("--json", action="store_true", help="Output execution plan and architecture docs in JSON format")
    gen_parser.add_argument("-o", "--output", type=str, help="File path to save the generated execution plan")

    # Command execution handler inside main()
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


"""
Cli module for OpenHarness.
Provides core functionality for the cli subsystem.
"""
from typing import Optional
import click
from local_agent_sandbox.core import LocalAgentSandbox, SandboxConfig
from local_agent_sandbox.pipeline_generator import AIPipelineGenerator


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """LocalAgentSandbox CLI - Sub-10ms Local Process Isolation for AI Coding Agents."""
    pass


# Alias for entry point / test imports
main = cli


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
@click.argument("prompt", required=False, default=None)
@click.option("--prompt", "-p", "prompt_opt", default=None, help="Natural language deployment prompt.")
@click.option("--output", "-o", default=None, help="Output file path to save execution plan.")
def ai_generate(prompt: Optional[str] = None, prompt_opt: Optional[str] = None, output: Optional[str] = None) -> None:
    """Generate an AI-driven CD pipeline execution plan and architecture documentation."""
    target_prompt = prompt_opt or prompt
    if not target_prompt:
        click.secho("Error: Missing prompt for AI pipeline generation.", fg="red", err=True)
        raise click.UsageError("Prompt argument or --prompt option is required.")

    generator = AIPipelineGenerator()
    plan = generator.generate(target_prompt)
    plan_json = plan.to_json(indent=2)

    click.echo(plan_json)

    if output:
        try:
            with open(output, "w", encoding="utf-8") as f:
                f.write(plan_json)
            click.secho(f"Successfully saved pipeline plan to '{output}'", fg="green")
        except Exception as e:
            click.secho(f"Failed to write output to '{output}': {e}", fg="red", err=True)


if __name__ == "__main__":
    cli()


# AI Pipeline Generation command group
    gen_parser = subparsers.add_parser("ai-generate", help="Generate AI deployment pipeline execution plan and architecture docs")
    gen_parser.add_argument("prompt", type=str, nargs="?", default="", help="Natural language prompt describing desired deployment state")
    gen_parser.add_argument("-p", "--prompt", dest="prompt_flag", type=str, help="Alternative flag for natural language prompt")
    gen_parser.add_argument("--provider", type=str, default="google", choices=["google", "openai", "anthropic"], help="LLM Provider adapter")
    gen_parser.add_argument("--model", type=str, default=None, help="LLM model name")
    gen_parser.add_argument("--api-key", type=str, default=None, help="API key for LLM provider")
    gen_parser.add_argument("--json", action="store_true", help="Output execution plan and architecture docs in JSON format")
    gen_parser.add_argument("-o", "--output", type=str, help="File path to save the generated execution plan")
