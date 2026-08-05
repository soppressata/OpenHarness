"""
Tests for Self-Healing Sandbox & Patch Generation Engine.
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from local_agent_sandbox.diagnostics import DiagnosisReport, BaseProviderAdapter, GoogleAdapter, OpenAIAdapter
from local_agent_sandbox.orchestrator import UniverseOrchestrator, UniverseStatus
from local_agent_sandbox.self_healing import (
    SelfHealingEngine,
    PatchGeneratorAgent,
    SelfHealingSandbox,
    GeneratedPatch,
    PatchVerificationResult,
    SelfHealingReport,
)
from local_agent_sandbox.self_healing_models import GeneratedPatch as ModularGeneratedPatch
from local_agent_sandbox.self_healing_subagents import PatchGeneratorAgent as ModularPatchGeneratorAgent
from local_agent_sandbox.self_healing_sandbox import SelfHealingSandbox as ModularSelfHealingSandbox
from local_agent_sandbox.cli import main as cli_main


def test_modular_imports():
    """Verify modular architecture components can be imported directly."""
    assert GeneratedPatch is ModularGeneratedPatch
    assert PatchGeneratorAgent is ModularPatchGeneratorAgent
    assert SelfHealingSandbox is ModularSelfHealingSandbox


def test_patch_generator_agent_llm_completion():
    agent = PatchGeneratorAgent(provider="openai", api_key="sk-test-key")

    mock_llm_json = {
        "explanation": "Added try-except block to catch zero division.",
        "patched_code": "def divide(a, b):\n    try:\n        return a / b\n    except ZeroDivisionError:\n        return 0.0\n"
    }

    mock_resp_data = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(mock_llm_json)
                }
            }
        ]
    }

    mock_http_resp = MagicMock()
    mock_http_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_http_resp.__enter__.return_value = mock_http_resp

    diagnosis = DiagnosisReport(
        step_id="step-div-1",
        step_name="Division Step",
        error_type="ZeroDivisionError",
        root_cause="division by zero in math module",
        summary="Zero division error occurred",
        suggested_fix="Add ZeroDivisionError guard",
        confidence_score=0.95,
        provider="openai",
    )

    orig_code = "def divide(a, b):\n    return a / b\n"

    with patch("urllib.request.urlopen", return_value=mock_http_resp):
        patch_obj = agent.generate_patch(
            diagnosis=diagnosis,
            target_file="math_utils.py",
            original_code=orig_code,
        )

    assert patch_obj.target_file == "math_utils.py"
    assert "ZeroDivisionError" in patch_obj.patched_code
    assert "a/math_utils.py" in patch_obj.diff
    assert "b/math_utils.py" in patch_obj.diff
    assert patch_obj.explanation == "Added try-except block to catch zero division."


def test_patch_generator_agent_heuristic_fallbacks():
    agent = PatchGeneratorAgent(provider="google")  # Unconfigured key triggers heuristic

    # Test ZeroDivisionError fallback
    diag_zero = DiagnosisReport(
        step_id="step-1",
        step_name="Math Step",
        error_type="ZeroDivisionError",
        root_cause="division by zero",
        summary="Zero division",
        suggested_fix="Check denominator",
    )
    orig_code_div = "def calculate(total, count):\n    return total / count\n"
    patch_div = agent.generate_patch(diag_zero, "calc.py", orig_code_div)
    assert "except ZeroDivisionError:" in patch_div.patched_code
    assert patch_div.diff != ""

    # Test KeyError fallback
    diag_key = DiagnosisReport(
        step_id="step-2",
        step_name="Dict Step",
        error_type="KeyError",
        root_cause="Missing key user_id",
        summary="KeyError user_id",
        suggested_fix="Use get method",
    )
    orig_code_dict = "def get_user(data):\n    val = data['user_id']\n    return val\n"
    patch_key = agent.generate_patch(diag_key, "user.py", orig_code_dict)
    assert ".get(" in patch_key.patched_code

    # Test ImportError fallback
    diag_imp = DiagnosisReport(
        step_id="step-3",
        step_name="Import Step",
        error_type="ImportError",
        root_cause="No module named missing_pkg",
        summary="ImportError missing_pkg",
        suggested_fix="Add import guard",
    )
    orig_code_imp = "import missing_pkg\n"
    patch_imp = agent.generate_patch(diag_imp, "imports.py", orig_code_imp)
    assert "try:" in patch_imp.patched_code
    assert "except ImportError:" in patch_imp.patched_code


def test_patch_generator_agent_custom_provider():
    """Verify PatchGeneratorAgent accepts a custom BaseProviderAdapter instance."""
    class DummyAdapter(BaseProviderAdapter):
        def generate_completion(self, prompt: str, system_prompt: str = "") -> str:
            return json.dumps({
                "explanation": "Custom adapter fix applied.",
                "patched_code": "def custom():\n    return True\n"
            })

    adapter = DummyAdapter(provider_name="custom")
    agent = PatchGeneratorAgent(provider=adapter)

    diagnosis = DiagnosisReport(
        step_id="step-custom",
        step_name="Custom Step",
        error_type="RuntimeError",
        root_cause="Custom error",
        summary="Custom summary",
        suggested_fix="Fix custom error",
    )

    patch_obj = agent.generate_patch(diagnosis, "custom.py", "def custom():\n    return False\n")
    assert patch_obj.explanation == "Custom adapter fix applied."
    assert "return True" in patch_obj.patched_code


def test_self_healing_sandbox_provision_and_verify():
    orchestrator = UniverseOrchestrator()
    sandbox_manager = SelfHealingSandbox(orchestrator=orchestrator)

    orig_code = "def compute(a, b):\n    return a / b\n"
    patched_code = "def compute(a, b):\n    if b == 0:\n        return 0.0\n    return a / b\n"
    diff = "--- a/math.py\n+++ b/math.py\n@@ -1,2 +1,4 @@\n def compute(a, b):\n+    if b == 0:\n+        return 0.0\n     return a / b\n"

    patch = GeneratedPatch(
        patch_id="patch-123",
        step_id="step-test",
        target_file="math.py",
        explanation="Added zero check before division.",
        original_code=orig_code,
        patched_code=patched_code,
        diff=diff,
    )

    # Test default verification
    res = sandbox_manager.provision_and_verify(patch=patch)
    assert res.verified is True
    assert res.test_passed is True
    assert "Provisioned environment" in res.test_output
    assert "Syntax check: Clean syntax validation passed" in res.test_output

    # Test custom test runner (passing)
    def custom_passing_runner(uv):
        val = uv.read_virtual_file("/math.py")
        return "def compute" in val

    res_pass = sandbox_manager.provision_and_verify(patch=patch, test_runner=custom_passing_runner)
    assert res_pass.verified is True
    assert "Custom test runner executed successfully" in res_pass.test_output

    # Test custom test runner (failing)
    def custom_failing_runner(uv):
        return False

    res_fail = sandbox_manager.provision_and_verify(patch=patch, test_runner=custom_failing_runner)
    assert res_fail.verified is False
    assert "Custom test runner failed" in res_fail.test_output


def test_self_healing_sandbox_syntax_error_handling():
    """Verify SelfHealingSandbox returns verified=False when patched code has syntax errors."""
    sandbox_manager = SelfHealingSandbox()
    invalid_patch = GeneratedPatch(
        patch_id="patch-syntax-err",
        step_id="step-err",
        target_file="broken.py",
        explanation="Broken patch",
        original_code="def ok(): pass\n",
        patched_code="def broken(:\n    invalid_syntax\n",
        diff="broken diff",
    )

    res = sandbox_manager.provision_and_verify(patch=invalid_patch)
    assert res.verified is False
    assert res.test_passed is False
    assert "Syntax check error" in res.test_output


def test_self_healing_engine_end_to_end():
    engine = SelfHealingEngine(provider="google")

    diagnosis = DiagnosisReport(
        step_id="step-pipeline-99",
        step_name="Pipeline Analytics Step",
        error_type="ZeroDivisionError",
        root_cause="ZeroDivisionError: float division by zero",
        summary="Division failure during metric computation",
        suggested_fix="Validate denominator non-zero prior to calculation",
        confidence_score=0.91,
    )

    orig_code = "def get_average(total, count):\n    return total / count\n"

    report = engine.remediate_failure(
        diagnosis=diagnosis,
        target_file="analytics/metrics.py",
        original_code=orig_code,
    )

    assert isinstance(report, SelfHealingReport)
    assert report.diagnosis.step_id == "step-pipeline-99"
    assert report.patch.target_file == "analytics/metrics.py"
    assert report.verification.verified is True
    assert report.review_status == "PENDING_DEVELOPER_REVIEW"

    # Test developer review text formatting
    review_text = report.format_review_text()
    assert "OpenHarness Self-Healing Sandbox & Verified Patch Report" in review_text
    assert "analytics/metrics.py" in review_text
    assert "VERIFIED PASS" in review_text
    assert "Unified Code Patch Diff" in review_text
    assert "b/analytics/metrics.py" in review_text

    # Test to_dict conversion
    report_dict = report.to_dict()
    assert report_dict["report_id"] == report.report_id
    assert report_dict["review_status"] == "PENDING_DEVELOPER_REVIEW"


def test_cli_self_heal_command(capsys):
    test_args = [
        "self-heal",
        "--target-file", "src/calculator.py",
        "--error-type", "ZeroDivisionError",
        "--root-cause", "Division by zero in formula",
        "--suggested-fix", "Guard denominator",
    ]

    ret = cli_main(test_args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "OpenHarness Self-Healing Sandbox & Verified Patch Report" in captured.out
    assert "src/calculator.py" in captured.out
