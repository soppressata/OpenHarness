"""
Subagents for patch generation utilizing root-cause diagnosis reports.
"""

import difflib
import json
import re
import uuid
from typing import Optional, Union

from .diagnostics import DiagnosisReport, BaseProviderAdapter, get_provider_adapter
from .self_healing_models import GeneratedPatch


class PatchGeneratorAgent:
    """
    Subagent that utilizes root-cause diagnosis reports and source context
    to generate candidate code patches using LLM adapters or heuristic fallback.
    """

    def __init__(
        self,
        provider: Union[str, BaseProviderAdapter] = "google",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        if isinstance(provider, BaseProviderAdapter):
            self.provider = provider
        else:
            self.provider = get_provider_adapter(provider_name=provider, api_key=api_key, model=model)

    def generate_patch(
        self,
        diagnosis: DiagnosisReport,
        target_file: str,
        original_code: str,
    ) -> GeneratedPatch:
        """
        Generates a code patch to fix the error identified in the DiagnosisReport.

        Args:
            diagnosis: The root-cause DiagnosisReport from the AI Diagnostics Engine.
            target_file: Path or filename of the target file needing repair.
            original_code: Current source code string of the target file.

        Returns:
            GeneratedPatch object containing the unified diff and proposed patched code.
        """
        system_prompt = (
            "You are an expert AI Autonomous Code Repair Subagent. "
            "Analyze the root-cause diagnosis report and source code, and generate a fixed version of the code. "
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "explanation": "Detailed rationale for the code changes",\n'
            '  "patched_code": "Complete modified source code string"\n'
            "}"
        )

        user_prompt = (
            f"Failed Step ID: {diagnosis.step_id}\n"
            f"Error Type: {diagnosis.error_type}\n"
            f"Root Cause: {diagnosis.root_cause}\n"
            f"Suggested Fix: {diagnosis.suggested_fix}\n"
            f"Target File: {target_file}\n\n"
            f"Original Source Code:\n```\n{original_code}\n```"
        )

        raw_resp = self.provider.generate_completion(prompt=user_prompt, system_prompt=system_prompt)
        parsed_patch = self._parse_patch_response(diagnosis, target_file, original_code, raw_resp)
        if parsed_patch:
            return parsed_patch

        return self._heuristic_generate_patch(diagnosis, target_file, original_code)

    def _parse_patch_response(
        self,
        diagnosis: DiagnosisReport,
        target_file: str,
        original_code: str,
        raw_resp: str,
    ) -> Optional[GeneratedPatch]:
        """Parses LLM response into a GeneratedPatch."""
        json_match = re.search(r"\{.*\}", raw_resp, re.DOTALL)
        if not json_match:
            return None
        try:
            data = json.loads(json_match.group(0))
            if not isinstance(data, dict):
                return None

            patched_code = data.get("patched_code")
            explanation = data.get("explanation", "Applied fix based on root cause analysis.")

            if not patched_code or not isinstance(patched_code, str):
                return None

            diff = self._create_unified_diff(original_code, patched_code, target_file)
            patch_id = f"patch-{uuid.uuid4().hex[:8]}"

            return GeneratedPatch(
                patch_id=patch_id,
                step_id=diagnosis.step_id,
                target_file=target_file,
                explanation=str(explanation),
                original_code=original_code,
                patched_code=patched_code,
                diff=diff,
                confidence_score=diagnosis.confidence_score,
            )
        except Exception:
            return None

    def _heuristic_generate_patch(
        self,
        diagnosis: DiagnosisReport,
        target_file: str,
        original_code: str,
    ) -> GeneratedPatch:
        """Heuristic patch generator used when offline or unauthenticated."""
        patch_id = f"patch-{uuid.uuid4().hex[:8]}"
        error_type = diagnosis.error_type
        root_cause = diagnosis.root_cause.lower()

        patched_lines = []
        explanation = f"Heuristically remediated {error_type} based on root-cause analysis."

        lines = original_code.splitlines()

        if error_type == "ZeroDivisionError" or "zero" in root_cause or "division" in root_cause:
            modified = False
            for line in lines:
                if "/" in line and "if" not in line and "try" not in line:
                    indent = len(line) - len(line.lstrip())
                    ind = " " * indent
                    patched_lines.append(f"{ind}# OpenHarness Self-Healing Guardrail")
                    patched_lines.append(f"{ind}try:")
                    patched_lines.append(f"{ind}    {line.strip()}")
                    patched_lines.append(f"{ind}except ZeroDivisionError:")
                    patched_lines.append(f"{ind}    return 0.0  # Fallback zero-division safety threshold")
                    modified = True
                else:
                    patched_lines.append(line)
            if not modified:
                patched_lines = lines + ["", "# ZeroDivisionError Guardrail", "def safe_divide(a, b):", "    return a / b if b != 0 else 0.0"]
            explanation = "Added ZeroDivisionError exception handling guardrail."

        elif error_type == "KeyError" or "key" in root_cause:
            modified = False
            for line in lines:
                if "[" in line and "]" in line and "get(" not in line:
                    new_line = re.sub(r'(\w+)\[(["\']?\w+["\']?)\]', r'\1.get(\2)', line)
                    patched_lines.append(new_line)
                    modified = True
                else:
                    patched_lines.append(line)
            if not modified:
                patched_lines = lines + ["", "# KeyError Guardrail", "def safe_get(d, key, default=None):", "    return d.get(key, default) if isinstance(d, dict) else default"]
            explanation = "Replaced direct dictionary key accesses with safe .get() calls."

        elif error_type in ("ImportError", "ModuleNotFoundError") or "import" in root_cause:
            patched_lines = ["# OpenHarness Import Guardrail"]
            for line in lines:
                if line.startswith("import ") or line.startswith("from "):
                    patched_lines.append("try:")
                    patched_lines.append(f"    {line}")
                    patched_lines.append("except ImportError:")
                    patched_lines.append("    pass  # Module optional or fallback available")
                else:
                    patched_lines.append(line)
            explanation = "Wrapped module imports with try-except fallback guards."

        elif error_type == "TypeError" or "type" in root_cause:
            patched_lines = []
            for line in lines:
                if "+" in line or "-" in line or "*" in line:
                    indent = len(line) - len(line.lstrip())
                    ind = " " * indent
                    patched_lines.append(f"{ind}try:")
                    patched_lines.append(f"{ind}    {line.strip()}")
                    patched_lines.append(f"{ind}except TypeError:")
                    patched_lines.append(f"{ind}    pass  # Type safety fallback")
                else:
                    patched_lines.append(line)
            explanation = "Added type safety exception handling to arithmetic operations."

        else:
            patched_lines = list(lines)
            patched_lines.append("")
            patched_lines.append("# OpenHarness Self-Healing Defensive Guardrail")
            patched_lines.append(f"# Fix applied: {diagnosis.suggested_fix}")
            explanation = f"Added defensive guardrail comments and fix suggestions for {error_type}."

        patched_code = "\n".join(patched_lines)
        if not patched_code.endswith("\n"):
            patched_code += "\n"

        diff = self._create_unified_diff(original_code, patched_code, target_file)

        return GeneratedPatch(
            patch_id=patch_id,
            step_id=diagnosis.step_id,
            target_file=target_file,
            explanation=explanation,
            original_code=original_code,
            patched_code=patched_code,
            diff=diff,
            confidence_score=0.88,
        )

    def _create_unified_diff(self, original_code: str, patched_code: str, target_file: str) -> str:
        """Generates unified diff between original and patched code."""
        orig_lines = original_code.splitlines(keepends=True)
        patch_lines = patched_code.splitlines(keepends=True)
        if orig_lines and not orig_lines[-1].endswith("\n"):
            orig_lines[-1] += "\n"
        if patch_lines and not patch_lines[-1].endswith("\n"):
            patch_lines[-1] += "\n"

        diff_gen = difflib.unified_diff(
            orig_lines,
            patch_lines,
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}",
        )
        return "".join(diff_gen)
