"""
AI Pipeline Generator Engine for OpenHarness / LocalAgentSandbox.
Generates functional pipeline execution plans and foundational architecture documentation
from natural language state declarations.
"""

import json
import os
import re
import time
import uuid
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field

from .diagnostics import BaseProviderAdapter, get_provider_adapter


class PipelineStep(BaseModel):
    """Represents a single step in the generated AI pipeline execution plan."""
    step_number: int
    name: str
    stage: str
    action: str
    validation: str


class PipelineExecutionPlan(BaseModel):
    """Execution plan for an AI-generated Continuous Delivery pipeline."""
    pipeline_id: str
    name: str
    target_state: str
    sla_target: str = "99.9% Uptime"
    cost_limit: str = "Uncapped"
    steps: List[PipelineStep] = Field(default_factory=list)


class ArchitectureDocs(BaseModel):
    """Foundational architecture documentation for the generated pipeline."""
    topology: str
    resilience: str
    cost_optimization: str
    security_baseline: str


class AIPipelineResult(BaseModel):
    """Complete result object containing execution plan and architecture documentation."""
    pipeline_id: str
    target_state: str
    provider: str
    execution_plan: PipelineExecutionPlan
    architecture_documentation: ArchitectureDocs
    timestamp: float = Field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary representation."""
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    def format_text(self) -> str:
        """Format the result as human-readable CLI text output."""
        lines = []
        lines.append("=" * 80)
        lines.append("🚀 OpenHarness AI Pipeline Execution Plan")
        lines.append("=" * 80)
        lines.append(f"Pipeline ID:   {self.pipeline_id}")
        lines.append(f"Target State:  {self.target_state}")
        lines.append(f"Provider:      {self.provider}")
        lines.append(f"SLA Target:    {self.execution_plan.sla_target}")
        lines.append(f"Cost Limit:    {self.execution_plan.cost_limit}")
        lines.append("")
        lines.append("-" * 80)
        lines.append("📋 Execution Plan Steps")
        lines.append("-" * 80)
        for s in self.execution_plan.steps:
            lines.append(f" {s.step_number:2d}. [{s.stage}] {s.name}")
            lines.append(f"     Action:     {s.action}")
            lines.append(f"     Validation: {s.validation}")
        lines.append("")
        lines.append("-" * 80)
        lines.append("🏗️ Foundational Architecture Documentation")
        lines.append("-" * 80)
        lines.append("### 1. Topology & Infrastructure")
        lines.append(self.architecture_documentation.topology)
        lines.append("")
        lines.append("### 2. Resilience & Self-Healing Strategy")
        lines.append(self.architecture_documentation.resilience)
        lines.append("")
        lines.append("### 3. Cost Optimization Controls")
        lines.append(self.architecture_documentation.cost_optimization)
        lines.append("")
        lines.append("### 4. Security & Compliance Baseline")
        lines.append(self.architecture_documentation.security_baseline)
        lines.append("=" * 80)
        return "\n".join(lines)


class AIPipelineGenerator:
    """
    AI Engine for generating autonomous deployment pipelines and architecture documentation
    from natural language state declarations.
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

    def generate_pipeline(self, prompt: str) -> AIPipelineResult:
        """
        Generates a functional pipeline execution plan and foundational architecture documentation
        from a natural language desired-state prompt.

        Args:
            prompt: Natural language string describing the target deployment state.

        Returns:
            AIPipelineResult containing structured execution plan and architecture docs.
        """
        system_prompt = (
            "You are the OpenHarness AI Engine for Continuous Delivery. "
            "Given a desired-state prompt, generate a structured deployment pipeline execution plan "
            "and foundational architecture documentation. "
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "sla_target": "string",\n'
            '  "cost_limit": "string",\n'
            '  "steps": [\n'
            '    {"step_number": 1, "name": "string", "stage": "string", "action": "string", "validation": "string"}\n'
            "  ],\n"
            '  "topology": "string",\n'
            '  "resilience": "string",\n'
            '  "cost_optimization": "string",\n'
            '  "security_baseline": "string"\n'
            "}"
        )

        raw_resp = self.provider.generate_completion(prompt=prompt, system_prompt=system_prompt)
        parsed_result = self._parse_completion_response(prompt, raw_resp)
        if parsed_result:
            return parsed_result

        return self._heuristic_generate(prompt)

    def _parse_completion_response(self, prompt: str, raw_resp: str) -> Optional[AIPipelineResult]:
        """Parses raw text completion from LLM provider into AIPipelineResult."""
        json_match = re.search(r"\{.*\}", raw_resp, re.DOTALL)
        if not json_match:
            return None
        try:
            data = json.loads(json_match.group(0))
            if not isinstance(data, dict):
                return None

            pipeline_id = f"pipe-{uuid.uuid4().hex[:8]}"
            steps_raw = data.get("steps", [])
            steps = []
            for idx, s in enumerate(steps_raw, 1):
                if isinstance(s, dict):
                    steps.append(
                        PipelineStep(
                            step_number=int(s.get("step_number", idx)),
                            name=str(s.get("name", f"Step {idx}")),
                            stage=str(s.get("stage", "Execution")),
                            action=str(s.get("action", "Perform task")),
                            validation=str(s.get("validation", "Verify success")),
                        )
                    )

            if not steps:
                return None

            plan = PipelineExecutionPlan(
                pipeline_id=pipeline_id,
                name=f"Pipeline: {prompt[:30]}",
                target_state=prompt,
                sla_target=str(data.get("sla_target", "99.9% Uptime")),
                cost_limit=str(data.get("cost_limit", "Uncapped")),
                steps=steps,
            )

            arch_docs = ArchitectureDocs(
                topology=str(data.get("topology", "Distributed multi-zone cluster architecture.")),
                resilience=str(data.get("resilience", "Automated self-healing and zero-downtime rollouts.")),
                cost_optimization=str(data.get("cost_optimization", "Dynamic auto-scaling and resource governance.")),
                security_baseline=str(data.get("security_baseline", "Zero-trust network policy and mTLS isolation.")),
            )

            return AIPipelineResult(
                pipeline_id=pipeline_id,
                target_state=prompt,
                provider=self.provider.get_provider_name(),
                execution_plan=plan,
                architecture_documentation=arch_docs,
            )
        except Exception:
            return None

    def _heuristic_generate(self, prompt: str) -> AIPipelineResult:
        """Heuristic generator used for deterministic pipeline creation when offline or unauthenticated."""
        pipeline_id = f"pipe-{uuid.uuid4().hex[:8]}"

        cloud_match = re.search(r"\b(AWS|GCP|Google Cloud|Azure|Kubernetes|K8s)\b", prompt, re.IGNORECASE)
        cloud = cloud_match.group(1).upper() if cloud_match else "AWS / Multi-Cloud"

        sla_match = re.search(r"(\d+(?:\.\d+)?%\s*(?:uptime|availability)?)", prompt, re.IGNORECASE)
        sla_target = sla_match.group(1) if sla_match else "99.99% Uptime"

        cost_match = re.search(r"(\$\d+(?:,\d+)*(?:\/mo|\/month|\s*per month)?)", prompt, re.IGNORECASE)
        cost_limit = cost_match.group(1) if cost_match else "$500/mo"

        svc_match = re.search(r"(?:deploy\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+to|\s+with|\s+keeping|\s*$)", prompt, re.IGNORECASE)
        target_name = svc_match.group(1).strip() if svc_match else "Target Microservice"

        steps = [
            PipelineStep(
                step_number=1,
                name=f"Infrastructure Provisioning on {cloud}",
                stage="Provisioning",
                action=f"Provision automated isolated Kubernetes cluster / VPC on {cloud} with zero-trust networking.",
                validation="Verify cloud environment status and compute quota allocation.",
            ),
            PipelineStep(
                step_number=2,
                name="Artifact Build & Vulnerability Scan",
                stage="Build",
                action=f"Build OCI container image for '{target_name}' and execute static vulnerability inspection.",
                validation="Ensure zero high/critical vulnerabilities before proceeding.",
            ),
            PipelineStep(
                step_number=3,
                name="Local Sandbox Smoke & Policy Verification",
                stage="Validation",
                action="Deploy container image into OpenHarness isolated local sandbox for contract testing.",
                validation="Pass zero-trust mesh security check and WASM boundary isolation test.",
            ),
            PipelineStep(
                step_number=4,
                name="Progressive Deployment & Traffic Shifting",
                stage="Deployment",
                action=f"Execute canary deployment to {cloud} with automated traffic shifting (10% -> 50% -> 100%).",
                validation=f"Confirm error rate < 0.01% and SLA latency target met during canary phase.",
            ),
            PipelineStep(
                step_number=5,
                name="Autonomous Health Monitoring & Cost Guardrail",
                stage="Observability",
                action=f"Attach AI Diagnostics Engine and cost monitor enforcing {cost_limit} threshold.",
                validation=f"Verify target SLA of {sla_target} with automated rollback active.",
            ),
        ]

        plan = PipelineExecutionPlan(
            pipeline_id=pipeline_id,
            name=f"Pipeline for {target_name}",
            target_state=prompt,
            sla_target=sla_target,
            cost_limit=cost_limit,
            steps=steps,
        )

        arch_docs = ArchitectureDocs(
            topology=(
                f"- Compute Layer: Containerized workload '{target_name}' deployed on high-availability {cloud} infrastructure.\n"
                "- Networking: Zero-trust mTLS mesh network with automated load balancing and ingress control.\n"
                "- Storage: Isolated copy-on-write virtual file system with audit trails."
            ),
            resilience=(
                f"- SLA Target: Enforces {sla_target} via automated multi-zone failover and health monitoring.\n"
                "- Self-Healing: AI Diagnostics Engine monitors logs in real time and triggers instant canary rollback upon error detection.\n"
                "- Fault Isolation: Sandboxed process execution prevents cascade failures across service dependencies."
            ),
            cost_optimization=(
                f"- Budget Limit: Strictly caps resource consumption to remain under {cost_limit}.\n"
                "- Auto-Scaling: Dynamic horizontal pod auto-scaling (HPA) scales compute instances based on real-time traffic demand.\n"
                "- Resource Efficiency: Reclaims idle sandbox environments automatically after execution."
            ),
            security_baseline=(
                "- Zero-Trust Mesh: All inter-service communications enforce mTLS encryption with automated certificate renewal.\n"
                "- Sandboxing: Hardened process jails restrict system calls, filesystem paths, and external network access.\n"
                "- Compliance Audit: Immutable event log recording all deployment steps and parameter state changes."
            ),
        )

        return AIPipelineResult(
            pipeline_id=pipeline_id,
            target_state=prompt,
            provider=f"{self.provider.get_provider_name()} (heuristic-engine)",
            execution_plan=plan,
            architecture_documentation=arch_docs,
        )
