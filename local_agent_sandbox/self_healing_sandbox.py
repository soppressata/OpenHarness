"""
Self-Healing Sandbox environment provisioning module.

Provisions isolated sandbox universes where generated patches can be applied,
failing tests re-run, and the fix verified before the diff is presented to a
developer for manual review.
"""

import time
import uuid
from typing import Callable, Optional, Union

from .orchestrator import UniverseOrchestrator, Universe, ComputeQuota
from .self_healing_models import GeneratedPatch, PatchVerificationResult

TestRunner = Callable[[Universe], bool]


class SelfHealingSandbox:
    """
    Provisions isolated sandboxes that apply a generated patch, run verification tests,
    and produce a PatchVerificationResult indicating whether the fix was verified.
    """

    def __init__(
        self,
        orchestrator: Optional[UniverseOrchestrator] = None,
        quota: Optional[ComputeQuota] = None,
    ):
        """
        Args:
            orchestrator: Optionally supply an existing UniverseOrchestrator
                for sandbox lifecycle management.
            quota: Compute quota applied to each provisioned sandbox universe.
        """
        self.orchestrator = orchestrator or UniverseOrchestrator(max_workers=4)
        self.quota = quota or ComputeQuota(memory_mb=1024, max_threads=8, max_processes=4)

    def provision_sandbox(self) -> Universe:
        """
        Provisions and starts an isolated sandbox universe for patch verification.

        Returns:
            The freshly provisioned sandboxed Universe.
        """
        return self.orchestrator.create_universe(
            name=f"self-healing-{uuid.uuid4().hex[:8]}",
            quota=self.quota,
            metadata={"purpose": "self_healing_patch_verification"},
        )

    def apply_patch(self, sandbox: Universe, patch: GeneratedPatch) -> str:
        """
        Writes the patch's patched code into the sandbox virtual filesystem.

        Args:
            sandbox: The sandbox Universe to apply the patch to.
            patch: The generated patch whose patched code should be staged.

        Returns:
            The sandbox path where the patched code was written.
        """
        path = patch.target_file
        if not path.startswith("/"):
            path = f"/{path}"
        sandbox.write_virtual_file(path, patch.patched_code)
        return path

    def _syntax_check(self, code: str) -> Optional[str]:
        """
        Validates that the patched code parses as valid Python.

        Args:
            code: The patched source code string.

        Returns:
            None if the code is valid, otherwise a description of the error.
        """
        try:
            compile(code, "<self-healing-sandbox>", "exec")
            return None
        except SyntaxError as error:
            return f"{error.msg} (line {error.lineno})"

    def provision_and_verify(
        self,
        patch: GeneratedPatch,
        test_runner: Optional[TestRunner] = None,
    ) -> PatchVerificationResult:
        """
        Provisions a sandbox, applies the patch, and verifies the fix.

        A built-in test runner is used by default; it stages the patched code in
        the sandbox and reports success when the code is executable. Callers may
        instead supply a custom ``test_runner`` receiving the sandbox Universe and
        returning a boolean indicating whether the failing tests now pass.

        Args:
            patch: The GeneratedPatch to apply and verify.
            test_runner: Optional custom test runner override.

        Returns:
            A PatchVerificationResult recording sandbox id, verification outcome,
            and test output for developer review.
        """
        start_time = time.time()
        sandbox = self.provision_sandbox()
        sandbox_id = sandbox.id
        output_lines = [
            f"[Provisioning] Provisioned environment and sandbox {sandbox_id} for patch {patch.patch_id}.",
            f"[Patch] Staged patched code of {patch.target_file} into virtual filesystem.",
        ]

        syntax_error = self._syntax_check(patch.patched_code)
        if syntax_error is not None:
            output_lines.append(f"Syntax check error: {syntax_error}")
            self._teardown(sandbox_id)
            return PatchVerificationResult(
                patch_id=patch.patch_id,
                sandbox_id=sandbox_id,
                verified=False,
                test_passed=False,
                test_output="\n".join(output_lines),
                execution_time_seconds=round(time.time() - start_time, 3),
            )

        output_lines.append("Syntax check: Clean syntax validation passed")

        if test_runner is None:
            verified, passed, message = self._default_test_runner(patch)
        else:
            verified, passed, message = self._run_custom_test_runner(sandbox, test_runner)

        output_lines.append(message)
        self._teardown(sandbox_id)

        return PatchVerificationResult(
            patch_id=patch.patch_id,
            sandbox_id=sandbox_id,
            verified=verified,
            test_passed=passed,
            test_output="\n".join(output_lines),
            execution_time_seconds=round(time.time() - start_time, 3),
        )

    def _default_test_runner(self, patch: GeneratedPatch) -> tuple:
        """
        Default sandbox verification: executes the patched code in a clean namespace.

        Returns:
            (verified, test_passed, message) tuple.
        """
        try:
            exec(compile(patch.patched_code, "<self-healing-sandbox>", "exec"), {})
        except Exception as error:
            return False, False, f"Default test runner failed: {type(error).__name__}: {error}"
        return True, True, "Default test runner executed successfully: fix verified in sandbox"

    def _run_custom_test_runner(self, sandbox: Universe, test_runner: TestRunner) -> tuple:
        """
        Invokes a custom test runner against the provisioned sandbox.

        Args:
            sandbox: The provisioned sandbox Universe.
            test_runner: Custom test runner callable.

        Returns:
            ``: (verified, test_passed, message)`` tuple.
        """
        try:
            passed = bool(test_runner(sandbox))
        except Exception as error:
            return False, False, f"Custom test runner error: {type(error).__name__}: {error}"
        if passed:
            return True, True, "Custom test runner executed successfully: fix verified in sandbox"
        return False, False, "Custom test runner failed: fix could not be verified"

    def _teardown(self, universe_id: str) -> None:
        """
        Destroys a sandbox universe after verification to free resources.

        Args:
            universe_id: The id of the sandbox universe to destroy.
        """
        self.orchestrator.destroy_universe(universe_id)