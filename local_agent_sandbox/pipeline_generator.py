"""
AI Pipeline Generator Engine for OpenHarness.
Provides declarative prompt-to-pipeline plan generation and architecture synthesis.
"""

import re
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class PipelineStep(BaseModel):
    """Represents a discrete step in the AI deployment pipeline execution plan."""
    id: int
    name: str
    action: str
    status: str = "pending"


class ExecutionPlan(BaseModel):
    """Execution plan containing SLA targets, cost limits, and sequential execution steps."""
    pipeline_id: str
    sla_target: str
    cost_limit: str
    steps: List[PipelineStep]


class ArchitectureDocumentation(BaseModel):
    """Foundational architecture documentation generated for the deployment pipeline."""
    topology: str
    resilience: str
    cost_optimization: str
    security_baseline: str


class AIPipelineResult(BaseModel):
    """Complete result object of the AI pipeline generation containing plan and architecture."""
    pipeline_id: str
    target_state: str
    provider: str
    execution_plan: ExecutionPlan
    architecture_documentation: ArchitectureDocumentation

    def to_dict(self) -> dict:
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
            lines.append(f" {s.id:2d}. [{s.name}] {s.action}")
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
    """AI Pipeline Generation Engine for synthesizing deployment execution plans."""

    def __init__(
        self,
        provider: str = "google",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """Initialize the generator with an AI provider.
        
        Args:
            provider: AI provider name (e.g. 'google', 'openai', 'anthropic').
            api_key: Optional API key for provider.
            model: Optional model name.
        """
        self.provider = provider
        self.api_key = api_key
        self.model = model

    def _extract_sla_target(self, prompt: str) -> str:
        """Extract SLA target string from prompt or return default."""
        match = re.search(r"(\d+(?:\.\d+)?%\s*(?:uptime|availability)?)", prompt, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            if "%" in val and "uptime" not in val.lower() and "availability" not in val.lower():
                val = f"{val} uptime"
            return val
        return "99.99% uptime"

    def _extract_cost_limit(self, prompt: str) -> str:
        """Extract cost limit string from prompt or return default."""
        match = re.search(r"(\$\d+(?:\.\d+)?(?:\/(?:mo|month|yr|year))?)", prompt, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return "$500/mo"

    def generate_pipeline(self, prompt: str) -> AIPipelineResult:
        """Generate a functional pipeline execution plan and architecture documentation from a natural language prompt.

        Args:
            prompt: Natural language description of desired target state.

        Returns:
            AIPipelineResult containing target state, provider, execution plan, and architecture docs.
        """
        pipe_id = f"pipe-{uuid.uuid4().hex[:8]}"
        sla_target = self._extract_sla_target(prompt)
        cost_limit = self._extract_cost_limit(prompt)

        steps = [
            PipelineStep(
                id=1,
                name="Parse Specification & Validate Target",
                action="Parse declarative target state specification and validate cloud target environment",
                status="pending"
            ),
            PipelineStep(
                id=2,
                name="IaC & Pipeline Synthesis",
                action="Synthesize infrastructure as code templates and container deployment manifests",
                status="pending"
            ),
            PipelineStep(
                id=3,
                name="Security Scan & Policy Verification",
                action="Execute automated static security scanning and policy compliance verification",
                status="pending"
            ),
            PipelineStep(
                id=4,
                name="Staging Deployment & Verification",
                action="Provision isolated staging container environment and execute automated integration tests",
                status="pending"
            ),
            PipelineStep(
                id=5,
                name="Canary Rollout & Self-Healing Monitor",
                action="Deploy to production cluster with automated canary rollback and self-healing telemetry monitoring",
                status="pending"
            )
        ]

        exec_plan = ExecutionPlan(
            pipeline_id=pipe_id,
            sla_target=sla_target,
            cost_limit=cost_limit,
            steps=steps
        )

        arch_doc = ArchitectureDocumentation(
            topology="Compute Layer: Multi-region container cluster with auto-scaling microservices topology",
            resilience=f"SLA Target: Guaranteed {sla_target} with automated failover and health probe monitoring",
            cost_optimization=f"Budget Limit: Constrained to {cost_limit} with spot instance scheduling and auto-rightsizing",
            security_baseline="Zero-Trust Mesh: Enforced mTLS encryption, least-privilege IAM roles, and secret rotation"
        )

        return AIPipelineResult(
            pipeline_id=pipe_id,
            target_state=prompt,
            provider=self.provider,
            execution_plan=exec_plan,
            architecture_documentation=arch_doc
        )
