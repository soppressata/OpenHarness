"""
CLI for the Self-Healing Sandbox & Patch Generation feature.

Provides a ``self-heal`` command that drives the end-to-end remediation engine
and prints the verified patch report for developer review.
"""

import os
import sys
import click

from .diagnostics import DiagnosisReport
from .self_healing import SelfHealingEngine


@click.group()
def harness_self_heal():
    """OpenHarness Self-Healing Sandbox CLI."""
    pass


@harness_self_heal.command("self-heal")
@click.option("--target-file", required=True, help="Path or filename of the target file needing repair.")
@click.option("--source-file", default=None, help="Optional path to a file containing the original source to patch.")
@click.option("--error-type", default="RuntimeError", help="Root-cause diagnosis error type.")
@click.option("--root-cause", default="Unspecified pipeline step failure", help="Diagnosed root cause description.")
@click.option("--suggested-fix", default="Review and repair the failing step", help="Suggested fix description.")
@click.option("--provider", default="google", help="LLM provider: google, openai, or anthropic.")
@click.option("--confidence", type=float, default=0.85, help="Diagnosis confidence score (0.0 - 1.0).")
def self_heal(target_file, source_file, error_type, root_cause, suggested_fix, provider, confidence):
    """
    Diagnose a failure, generate a patch via subagents, verify it in an isolated
    sandbox, and present the verified diff for developer review.
    """
    original_code = ""
    if source_file and os.path.exists(source_file):
        with open(source_file, "r", encoding="utf-8") as handle:
            original_code = handle.read()
    elif os.path.exists(target_file):
        with open(target_file, "r", encoding="utf-8") as handle:
            original_code = handle.read()

    diagnosis = DiagnosisReport(
        step_id="cli-self-heal-1",
        step_name=target_file,
        error_type=error_type,
        root_cause=root_cause,
        summary=f"{error_type} detected during pipeline step execution.",
        suggested_fix=suggested_fix,
        confidence_score=confidence,
    )

    engine = SelfHealingEngine(provider=provider)
    report = engine.remediate_failure(
        diagnosis=diagnosis,
        target_file=target_file,
        original_code=original_code,
    )

    click.echo(report.format_review_text())
    return 0


def main(argv=None):
    """
    CLI entry point for the self-healing command group.

    Args:
        argv: Optional argument list (including the subcommand name). Defaults to
            ``sys.argv[1:]``.

    Returns:
        The exit code of the invoked subcommand (0 on success).
    """
    args = list(argv) if argv is not None else list(sys.argv[1:])
    return harness_self_heal.main(args=args, prog_name="openharness-self-heal", standalone_mode=False)


if __name__ == "__main__":
    sys.exit(main())