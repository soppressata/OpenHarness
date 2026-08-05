"""
Self-Healing Sandbox & Patch Generation Engine for OpenHarness / LocalAgentSandbox.

Utilizes AI root-cause diagnosis reports to generate code patches via subagents,
provisions isolated sandbox environments to apply patches and re-run failing
tests, and presents verified diffs to developers for manual review.
"""

import time
import uuid
from typing import Optional, Union, Any, Callable

import time as _time

from .diagnostics import DiagnosisReport, BaseProviderAdapter
from .self_healing_subagents import PatchGeneratorAgent
from .self_healing_sandbox import SelfHealingSandbox, TestRunner
from .self_healing_models import (
    GeneratedPatch,
    PatchVerificationResult,
    SelfHealingReport,
)

__all__ = [
    "SelfHealingEngine",
    "PatchGeneratorAgent",
    "SelfHealingSandbox",
    "GeneratedPatch",
    "PatchVerificationResult",
    "SelfHealingReport",
]


class SelfHealingEngine:
    """
    End-to-end remediation engine that orchestrates patch generation subagents,
    sandbox provisioning, and patch verification to produce verified diffs for
    developer review.
    """

    def __init__(
        self,
        provider: Union[str, BaseProviderAdapter] = "google",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        orchestrator: Any = None,
        sandbox: Optional[SelfHealingSandbox] = None,
    ):
        """
        Args:
            provider: LLM provider name or a BaseProviderAdapter instance used by the
                PatchGeneratorAgent subagent.
            api_key: Optional API key for the configured provider.
            model: Optional model identifier for the configured provider.
            orchestrator: Optional UniverseOrchestrator for sandbox provisioning.
            sandbox: Optional pre-constructed SelfHealingSandbox instance.
        """
        self.patch_agent = PatchGeneratorAgent(provider=provider, api_key=api_key, model=model)
        self.sandbox = sandbox or SelfHealingSandbox(orchestrator=orchestrator)

    def remediate_failure(
        self,
        diagnosis: DiagnosisReport,
        target_file: str,
        original_code: str,
        test_runner: Optional[TestRunner] = None,
        review_status: str = "PENDING_DEVELOPER_REVIEW",
    ) -> SelfHealingReport:
        """
        Generates a patch for the diagnosed failure, provisions a sandbox to verify
        the fix, and packages the results into a developer review report.

        Args:
            diagnosis: The root-cause DiagnosisReport from the AI Diagnostics Engine.
            target_file: Path or filename of the target file needing repair.
            original_code: Current source code string of the target file.
            test_runner: Optional custom test runner for sandbox verification.
            review_status: Initial review status of the generated report.

        Returns:
            A SelfHealingReport containing the diagnosis, patch, and verification
            result, ready for developer manual review.
        """
        patch = self.patch_agent.generate_patch(
            diagnosis=diagnosis,
            target_file=target_file,
            original_code=original_code,
        )

        verification = self.sandbox.provision_and_verify(patch=patch, test_runner=test_runner)

        return SelfHealingReport(
            report_id=f"report-{uuid.uuid4().hex[:8]}",
            diagnosis=diagnosis,
            patch=patch,
            verification=verification,
            review_status=review_status,
            timestamp=_time.time(),
        )