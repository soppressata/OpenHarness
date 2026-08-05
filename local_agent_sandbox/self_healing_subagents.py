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
            f"Original Source Code:\n
